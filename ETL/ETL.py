import pyspark
import os
from itertools import chain
from pyspark.sql import functions as F
from pyspark.sql import SparkSession
from pyspark.sql.types import *
from pyspark.sql.window import Window
from deep_translator import GoogleTranslator
from pyspark.sql.functions import *
from IPython.display import display, HTML
display(HTML("<style>pre { white-space: pre !important; }</style>"))
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType

# Initialize Spark Session
spark = SparkSession.builder \
    .appName("ETL_Process") \
    .config("spark.jars", r"P:\Career\Data Engineering\ITI-DE\Graduation Project\Steps\ETL\postgresql-42.7.5.jar") \
    .config("spark.driver.memory", "8g") \
    .getOrCreate()

# JDBC URL and properties
postgres_url = "jdbc:postgresql://localhost:5432/FashionRetailDB"
postgres_properties = {
    "user": "postgres",
    "password": "1699",
    "driver": "org.postgresql.Driver"
}

# Extract tables from PostgreSQL
df_categories = spark.read.jdbc(url=postgres_url, table="normalizedretail.categories", properties=postgres_properties)
df_currency = spark.read.jdbc(url=postgres_url, table="normalizedretail.currency", properties=postgres_properties)
df_customers = spark.read.jdbc(url=postgres_url, table="normalizedretail.customers", properties=postgres_properties)
df_discounts = spark.read.jdbc(url=postgres_url, table="normalizedretail.discounts", properties=postgres_properties)
df_employees = spark.read.jdbc(url=postgres_url, table="normalizedretail.employees", properties=postgres_properties)
df_location = spark.read.jdbc(url=postgres_url, table="normalizedretail.location", properties=postgres_properties)
df_productattribute = spark.read.jdbc(url=postgres_url, table="normalizedretail.productattribute", properties=postgres_properties)
df_products = spark.read.jdbc(url=postgres_url, table="normalizedretail.products", properties=postgres_properties)
df_stores = spark.read.jdbc(url=postgres_url, table="normalizedretail.stores", properties=postgres_properties)

df_transactions1 = spark.read \
    .format("jdbc") \
    .option("url", postgres_url) \
    .option("dbtable", "normalizedretail.transactions") \
    .option("user", "postgres") \
    .option("password", "1699") \
    .option("driver", "org.postgresql.Driver") \
    .option("partitionColumn", "transactionid") \
    .option("lowerBound", "1") \
    .option("upperBound", "100000") \
    .option("numPartitions", "10") \
    .load()

df_transactionlines = spark.read \
    .format("jdbc") \
    .option("url", postgres_url) \
    .option("dbtable", "normalizedretail.transactionlines") \
    .option("user", "postgres") \
    .option("password", "1699") \
    .option("driver", "org.postgresql.Driver") \
    .option("partitionColumn", "transactionid") \
    .option("lowerBound", "1") \
    .option("upperBound", "100000") \
    .option("numPartitions", "10") \
    .load()

# Read CSV file
spark.conf.set("spark.sql.legacy.timeParserPolicy", "LEGACY")

transactions_schema = StructType([
    StructField("Invoice ID", StringType(), False),
    StructField("Line", IntegerType(), False),
    StructField("Customer ID", IntegerType(), True),
    StructField("Product ID", IntegerType(), True),
    StructField("Size", StringType(), True),
    StructField("Color", StringType(), True),
    StructField("Unit Price", FloatType(), True),
    StructField("Quantity", IntegerType(), True),
    StructField("Date", StringType(), True),
    StructField("Discount", FloatType(), True),
    StructField("Line Total", FloatType(), True),
    StructField("Store ID", IntegerType(), True),
    StructField("Employee ID", IntegerType(), True),
    StructField("Currency", StringType(), True),
    StructField("Currency Symbol", StringType(), True),
    StructField("SKU", StringType(), True),
    StructField("Transaction Type", StringType(), True),
    StructField("Payment Method", StringType(), True),
    StructField("Invoice Total", FloatType(), True)
])

file2 = r"P:\Career\Data Engineering\ITI-DE\Graduation Project\Data\CSVs\Transactions2.csv"

df_transactions2 = spark.read.option("header", "true").schema(transactions_schema).csv(file2)


# Customers Table Transformation
df_customers = df_customers \
    .withColumnRenamed("customer_id", "Customer ID") \
    .withColumnRenamed("locid", "Location ID") \
    .withColumnRenamed("job_title", "Job Title") \
    .withColumnRenamed("gender", "Gender") \
    .withColumnRenamed("date_of_birth", "Date of Birth") \
    .withColumn("Name", col("name")) \
    .withColumn("Email", lower(col("email"))) \
    .withColumn("Location ID", trim(col("Location ID")).cast("int")) \
    .withColumn("Telephone", regexp_replace(col("telephone"), "[^0-9]", "")) \
    .withColumn("Gender", when(upper(col("Gender")) == "M", lit("M")).when(upper(col("Gender")) == "F", lit("F")).otherwise(lit("U"))) \
    .withColumn("Date of Birth", to_date(col("Date of Birth"), "yyyy-MM-dd"))

df_customers = df_customers.fillna({"Job Title": "Not Specified"})

df_customers = df_customers.withColumn(
    "Email", 
    regexp_replace("Email", "@fake.*", "@gmail.com")
)

# Products Table Transformation
df_products = df_products \
    .withColumnRenamed("productid", "Product ID") \
    .withColumnRenamed("categoryid", "Category ID") \
    .withColumn("Product ID", trim(col("Product ID")).cast("int")) \
    .withColumn("Category ID", trim(col("Category ID")).cast("int")) \
    .withColumn("Description EN", trim(col("Description EN")))

df_products = df_products.drop("Description ZH", "Description PT", "Description DE", "Description FR", "Description ES")

# Product Attributes Table
df_productattribute = df_productattribute \
    .withColumnRenamed("prod_attributeid", "Product Attribute ID") \
    .withColumnRenamed("productid", "Product ID") \
    .withColumnRenamed("color", "Color") \
    .withColumnRenamed("sizes", "Sizes") \
    .withColumnRenamed("productioncost", "Production Cost") \
    .withColumnRenamed("sku", "SKU") \
    .withColumn("Product ID", trim(col("Product ID")).cast("int")) \
    .withColumn("Product Attribute ID", trim(col("Product Attribute ID")).cast("int")) \
    .withColumn("Color", trim(col("Color"))) \
    .withColumn("Sizes", trim(col("Sizes"))) \
    .withColumn("Production Cost", trim(col("Production Cost")).cast(DecimalType(10,2))) \
    .withColumn("SKU", trim(col("SKU")))

# Employees Table
df_employees = df_employees \
    .withColumnRenamed("employeeid", "employeeid_pk_bk") \
    .withColumn("name", trim(col("name"))) \
    .withColumn("position", trim(col("position"))) \
    .withColumn("employeeid_pk_bk", col("employeeid_pk_bk").cast("int")) \
    .withColumn("storeid", col("storeid").cast("int"))

# Currency Table
df_currency = df_currency \
    .withColumnRenamed("currencyid", "Currency ID") \
    .withColumnRenamed("currency", "Currency") \
    .withColumn("Currency", trim(col("Currency"))) \
    .withColumn("Currency ID", col("Currency ID").cast("int"))

df_currency = df_currency.drop("currencysymbol")

# Location Table
df_location = df_location \
    .withColumnRenamed("locid", "Location ID") \
    .withColumnRenamed("city", "City") \
    .withColumnRenamed("country", "Country") \
    .withColumn("City", trim(col("City"))) \
    .withColumn("Country", trim(col("Country"))) \
    .withColumn("Location ID", col("Location ID").cast("int"))


# Categories Table
df_categories = df_categories \
    .withColumn("category", trim(col("category"))) \
    .withColumn("subcategory", trim(col("subcategory"))) \
    .withColumnRenamed("categoryid", "Category ID") \
    .withColumnRenamed("category", "Category") \
    .withColumnRenamed("subcategory", "SubCategory") \
    .withColumn("Category ID", col("Category ID").cast("int"))

# Stores Table
df_stores = df_stores \
    .withColumnRenamed("storename", "Store Name") \
    .withColumnRenamed("zipcode", "Zip Code") \
    .withColumnRenamed("storeid", "Store ID") \
    .withColumnRenamed("latitude", "Latitude") \
    .withColumnRenamed("longitude", "Longitude") \
    .withColumnRenamed("locid", "Location ID") \
    .withColumnRenamed("numberofemployees", "Number of Employees") \
    .withColumn("Store Name", trim(col("Store Name"))) \
    .withColumn("Zip Code", trim(col("Zip Code"))) \
    .withColumn("Store ID", col("Store ID").cast("int")) \
    .withColumn("Location ID", col("Location ID").cast("int")) \
    .withColumn("Number of Employees", col("Number of Employees").cast("int")) \
    .withColumn("Latitude", col("Latitude").cast(DecimalType(10,6))) \
    .withColumn("Longitude", col("Longitude").cast(DecimalType(10,6)))

# Discounts Table
df_discounts = df_discounts \
    .withColumn("discountid", trim(col("discountid")).cast("int")) \
    .withColumn("categoryid", trim(col("categoryid")).cast("int")) \
    .withColumn("Start", to_date(trim(col("Start")), "yyyy-MM-dd")) \
    .withColumn("End", to_date(trim(col("End")), "yyyy-MM-dd")) \
    .withColumn("discount", trim(col("discount")).cast(DecimalType(5,2))) \
    .withColumn("description", trim(col("description"))) \
    .withColumnRenamed("discountid", "Discount ID") \
    .withColumnRenamed("categoryid", "Category ID") \
    .withColumnRenamed("Start", "Start Date") \
    .withColumnRenamed("End", "End Date") \
    .withColumnRenamed("Discount", "Discount") \
    .withColumnRenamed("Description", "Description")                

df_discounts = df_discounts.drop("Description")

# Store Name and Country Translation
shop_translation = {
    "Store 上海": "Store Shanghai",
    "Store 北京": "Store Beijing",
    "Store 广州": "Store Guangzhou",
    "Store 深圳": "Store Shenzhen",
    "Store 重庆": "Store Chongqing"
}

country_dict = {
    "España": "Spain",
    "Deutschland": "Germany",
    "中国": "China",
    "France": "France",
    "Portugal": "Portugal",
    "United Kingdom": "United Kingdom",
    "United States": "United States",
}

city_translation = {
    "Köln": "Cologne",
    "上海": "Shanghai",
    "深圳": "Shenzhen",
    "北京": "Beijing",
    "重庆": "Chongqing",
    "广州": "Guangzhou",
    "München": "Munich",
    "Frankfurt am Main": "Frankfurt",
    "Guimarães": "Guimaraes",
    "Sevilla": "Seville",
    "Valencia": "Valencia",
    "Madrid": "Madrid",
    "Barcelona": "Barcelona"
}
'''
country_map = create_map([lit(x) for x in chain(*country_translation.items())])
city_map = create_map([lit(x) for x in chain(*city_translation.items())])
shop_map = create_map([lit(x) for x in chain(*shop_translation.items())])

stores_dwh = df_stores.withColumn("country", coalesce(country_map.getItem(col("country")), col("country"))) \
    .withColumn("city", coalesce(city_map.getItem(col("city")), col("city"))) \
    .withColumn("storename", coalesce(shop_map.getItem(col("storename")), col("storename")))'''

'''
@udf(StringType())
def map_country(country):
    if country in country_dict:
        return country_dict[country]
    return country  # fallback original
 
# Then apply the UDF
stores_dwh = df_stores.withColumn("country", map_country(col("country"))) 
'''

# Transactions Table (CSV) Transformation
df_transactionscsv = df_transactions2 \
    .withColumn("Invoice ID", col("Invoice ID").cast(StringType())) \
    .withColumn("Line", col("Line").cast(IntegerType())) \
    .withColumn("Customer ID", col("Customer ID").cast(StringType())) \
    .withColumn("Product ID", col("Product ID").cast(StringType())) \
    .withColumn("Size", col("Size").cast(StringType())) \
    .withColumn("Color", col("Color").cast(StringType())) \
    .withColumn("Unit Price", col("Unit Price").cast(DoubleType())) \
    .withColumn("Quantity", col("Quantity").cast(IntegerType())) \
    .withColumn("Date", to_timestamp(col("Date"), "dd/MM/yyyy HH:mm").cast(TimestampType())) \
    .withColumn("Discount", col("Discount").cast(DoubleType())) \
    .withColumn("Line Total", col("Line Total").cast(DecimalType(10,2))) \
    .withColumn("Store ID", col("Store ID").cast(StringType())) \
    .withColumn("Employee ID", col("Employee ID").cast(StringType())) \
    .withColumn("Currency", col("Currency").cast(StringType())) \
    .withColumn("Currency Symbol", col("Currency Symbol").cast(StringType())) \
    .withColumn("SKU", col("SKU").cast(StringType())) \
    .withColumn("Transaction Type", col("Transaction Type").cast(StringType())) \
    .withColumn("Payment Method", col("Payment Method").cast(StringType())) \
    .withColumn("Invoice Total", col("Invoice Total").cast(DecimalType(10,2))) \
    .drop("Date")

# Transactions Table (DB) Transformation
df_transactionsdb = df_transactions1 \
    .withColumnRenamed("transactionid", "Transaction ID") \
    .withColumnRenamed("invoiceid", "Invoice ID") \
    .withColumnRenamed("transactiondate", "Transaction Date") \
    .withColumnRenamed("transactiontype", "Transaction Type") \
    .withColumnRenamed("discountid", "Discount ID") \
    .withColumnRenamed("paymentmethod", "Payment Method") \
    .withColumnRenamed("invoicetotal", "Invoice Total") \
    .withColumnRenamed("customerid", "Customer ID") \
    .withColumnRenamed("storeid", "Store ID") \
    .withColumnRenamed("employeeid", "Employee ID") \
    .withColumnRenamed("currencyid", "Currency ID") \
    .withColumn("Transaction ID", trim(col("Transaction ID")).cast("int")) \
    .withColumn("Invoice ID", trim(col("Invoice ID")).cast("string")) \
    .withColumn("Transaction Date", to_date("Transaction Date")) \
    .withColumn("Transaction Type", trim(col("Transaction Type")).cast("string")) \
    .withColumn("Discount ID", trim(col("Discount ID")).cast("int")) \
    .withColumn("Payment Method", trim(col("Payment Method")).cast("string")) \
    .withColumn("Invoice Total", trim(col("Invoice Total")).cast(DecimalType(10,2))) \
    .withColumn("Customer ID", trim(col("Customer ID")).cast("int")) \
    .withColumn("Store ID", trim(col("Store ID")).cast("int")) \
    .withColumn("Employee ID", trim(col("Employee ID")).cast("int")) \
    .withColumn("Currency ID", trim(col("Currency ID")).cast("int"))

# Transaction Lines Table Transformation
df_transactionlines = df_transactionlines \
    .withColumnRenamed("transactionlineid", "Transaction Line ID") \
    .withColumnRenamed("transactionid", "Transaction ID") \
    .withColumnRenamed("productid", "Product ID") \
    .withColumnRenamed("unitprice", "Unit Price") \
    .withColumnRenamed("quantity", "Quantity") \
    .withColumnRenamed("discount", "Discount") \
    .withColumnRenamed("linetotal", "Line Total") \
    .withColumnRenamed("line", "Line") \
    .withColumn("Transaction ID", trim(col("Transaction ID")).cast("int")) \
    .withColumn("Transaction Line ID", trim(col("Transaction Line ID")).cast("int")) \
    .withColumn("Product ID", trim(col("Product ID"))) \
    .withColumn("Unit Price", trim(col("Unit Price")).cast(DecimalType(10,2))) \
    .withColumn("Quantity", trim(col("Quantity")).cast("int")) \
    .withColumn("Line", trim(col("Line")).cast("int")) \
    .withColumn("Discount", trim(col("Discount")).cast("double")) \
    .withColumn("Line Total", trim(col("Line Total")).cast(DecimalType(10,2)))

# Customers DWH
customers_dwh = df_customers.join(df_location, "Location ID", "left").select(
    df_customers["Customer ID"].alias("customerid_pk_bk"),
    df_customers["Name"].alias("name"),
    df_customers["Email"].alias("email"),
    df_customers["Telephone"].alias("telephone"),
    df_location["City"].alias("city"),
    df_location["Country"].alias("country"),
    df_customers["Gender"].alias("gender"),
    df_customers["Date of Birth"].alias("date_of_birth"),
    df_customers["Job Title"].alias("job_title")
)

# Discounts DWH
discounts_dwh = df_discounts.join(df_categories, "Category ID", "left").select(
    df_discounts["Discount ID"].alias("discountid_pk_bk"),
    df_discounts["Start Date"].alias("startdate"),
    df_discounts["End Date"].alias("enddate"),
    df_discounts["Discount"].alias("discount"),
    df_categories["Category"].alias("category"),
    df_categories["SubCategory"].alias("subcategory")
)

# Products DWH
prod_with_cat = df_products.join(df_categories, "Category ID", "left")
prod_with_price = prod_with_cat.join(df_transactionlines, "Product ID", "left").groupBy(
    "Product ID", "Category", "SubCategory", "Description EN"
).agg(
    {"Unit Price": "first"}
).withColumnRenamed("first(Unit Price)", "Unit Price")

products_dwh_temp = prod_with_price.join(df_productattribute.alias("attr"), "Product ID", "left").select(
    col("Product ID"),
    col("Unit Price"),
    col("Category"),
    col("SubCategory"),
    col("Description EN"),
    col("attr.Color"),
    col("attr.Sizes"),
    col("attr.Production Cost"),
    col("attr.SKU")
)

products_dwh = products_dwh_temp.select(
    col("Product ID").alias("productid_pk_bk"),
    col("Category").alias("category"),
    col("SubCategory").alias("subcategory"),
    col("Description EN").alias("descriptionen"),
    coalesce(col("Color"), lit("N/A")).alias("color"),
    coalesce(col("Sizes"), lit("UNKNOWN")).alias("sizes"),
    coalesce(col("Production Cost"), lit(0.0)).alias("productioncost"),
    coalesce(col("SKU"), lit("NO_SKU")).alias("sku"),
    lit("USD").alias("Currency"),
    coalesce(col("Unit Price"), lit(0.0)).alias("unitprice")
)

# Stores DWH
stores_dwh = df_stores.join(df_location, "Location ID", "left").select(
    df_stores["Store ID"].alias("storeid_pk_bk"),
    df_location["Country"].alias("country"),
    df_location["City"].alias("city"),
    df_stores["Store Name"].alias("storename"),
    df_stores["Number of Employees"].alias("numberofemployees"),
    df_stores["Zip Code"].alias("zipcode"),
    df_stores["Latitude"].alias("latitude"),
    df_stores["Longitude"].alias("longitude")
)

# Employees DWH
employees_dwh = df_employees.select(
    "employeeid_pk_bk",
    "storeid",
    "name",
    "position"
)

# Date DWH
date_dwh = df_transactionsdb.select(to_date("Transaction Date").alias("date")).distinct()
date_dwh = date_dwh.select(
    col("date"),
    dayofmonth("date").alias("day"),
    month("date").alias("month"),
    date_format("date", "MMMM").alias("month_name"),
    year("date").alias("year"),
    dayofweek("date").alias("day_of_week"),
    date_format("date", "EEEE").alias("day_name"),
    weekofyear("date").alias("week_of_year"),
    when(dayofweek("date").isin(1, 7), lit(True)).otherwise(lit(False)).alias("is_weekend"),
    quarter("date").alias("quarter"),
    date_format("date", "yyyy-MM").alias("year_month")
)

windowSpec = Window.orderBy("date")
date_dwh = date_dwh.withColumn("date_pk_bk", row_number().over(windowSpec))

# Transactions Fact Table
# Step 1: Join df_transactionsdb with customer, store, employee, currency, and discount info
transactions_full_df = df_transactionsdb \
    .join(df_customers, on="Customer ID", how="inner") \
    .join(df_stores, on="Store ID", how="inner") \
    .join(df_employees, df_transactionsdb["Employee ID"] == df_employees["employeeid_pk_bk"], "inner") \
    .join(df_currency, on="Currency ID", how="inner") \
    .join(df_discounts, on="Discount ID", how="left") \
    .select(
        df_transactionsdb["Transaction ID"],
        df_transactionsdb["Invoice ID"],
        df_transactionsdb["Transaction Type"],
        df_transactionsdb["Payment Method"],
        df_transactionsdb["Invoice Total"],
        df_transactionsdb["Transaction Date"],
        df_transactionsdb["Customer ID"],
        df_transactionsdb["Store ID"],
        df_transactionsdb["Employee ID"],
        df_transactionsdb["Discount ID"]
    )

# Step 2: Join df_transactionlines with df_productattribute and df_products & categories
transaction_lines_cat = df_transactionlines \
    .join(df_productattribute, on="Product ID", how="inner") \
    .join(df_products, on="Product ID", how="left") \
    .join(df_categories, df_products["Category ID"] == df_categories["Category ID"], "left") \
    .select(
        df_transactionlines["Transaction ID"],
        df_transactionlines["Transaction Line ID"],
        df_transactionlines["Line"],
        df_transactionlines["Quantity"],
        df_transactionlines["Line Total"],
        df_transactionlines["Product ID"],
        df_productattribute["Color"],
        df_productattribute["Sizes"],
        df_productattribute["SKU"]
    )

# Step 3: Join with date_dwh to get surrogate date key
transactions_full_df = transactions_full_df \
    .join(date_dwh, transactions_full_df["Transaction Date"] == date_dwh["date"], "left") \
    .select(
        transactions_full_df["Transaction ID"],
        date_dwh["date"].alias("date_pk_bk"),
        transactions_full_df["Store ID"],
        transactions_full_df["Employee ID"].alias("employeeid_pk_bk"),
        transactions_full_df["Customer ID"].alias("customerid_pk_bk"),
        transactions_full_df["Discount ID"].alias("discountid_pk_bk"),
        transactions_full_df["Invoice ID"].alias("invoiceid"),
        transactions_full_df["Transaction Type"].alias("transactiontype"),
        transactions_full_df["Payment Method"].alias("paymentmethod"),
        transactions_full_df["Invoice Total"].alias("invoicetotal")
    )

# Step 4: Join the previous two dfs
transactions_dwh = transaction_lines_cat \
    .join(transactions_full_df, on="Transaction ID", how="inner") \
    .select(
        col("Transaction ID").alias("transactionid"),
        col("date_pk_bk"),
        col("Store ID").alias("storeid_pk_bk"),
        col("employeeid_pk_bk"),
        col("customerid_pk_bk"),
        col("Product ID").alias("productid_pk_bk"),
        col("discountid_pk_bk"),
        col("invoiceid"),
        col("transactiontype"),
        col("Line").alias("line"),
        col("Line Total").alias("linetotal"),
        col("paymentmethod"),
        col("invoicetotal"),
        col("Quantity").alias("quantity"),
        col("Color").alias("color"),
        col("Sizes").alias("size"),
        col("SKU").alias("sku")
    )
# Final Schema Join the df with Transactions CSV File
transactions_dwh = transactions_dwh \
    .join(df_transactionscsv,
          (transactions_dwh["invoiceid"] == df_transactionscsv["Invoice ID"]) &
          (transactions_dwh["line"] == df_transactionscsv["Line"]) &
          (transactions_dwh["customerid_pk_bk"] == df_transactionscsv["Customer ID"]) &
          (transactions_dwh["productid_pk_bk"] == df_transactionscsv["Product ID"]),
          how="left") \
    .select(
        transactions_dwh["*"]) 

transactions_dwh = transactions_dwh.fillna({"discountid_pk_bk": 0})

# Save Date DWH
pandas_df = date_dwh.toPandas()
pandas_df.to_csv(r"P:/Career/Data Engineering/ITI-DE/Graduation Project/Data/Data Destinations/Date.csv", index=False)

# Save Customers DWH
pandas_df = customers_dwh.toPandas()
pandas_df.to_csv(r"P:/Career/Data Engineering/ITI-DE/Graduation Project/Data/Data Destinations/Customers.csv", index=False)

# Save Discounts DWH
pandas_df = discounts_dwh.toPandas()
pandas_df.to_csv(r"P:/Career/Data Engineering/ITI-DE/Graduation Project/Data/Data Destinations/Discounts.csv", index=False)

# Save Products DWH
pandas_df = products_dwh.toPandas()
pandas_df.to_csv(r"P:/Career/Data Engineering/ITI-DE/Graduation Project/Data/Data Destinations/Products.csv", index=False)

# Save Stores DWH
pandas_df = stores_dwh.toPandas()
pandas_df.to_csv(r"P:/Career/Data Engineering/ITI-DE/Graduation Project/Data/Data Destinations/Stores.csv", index=False)

# Save Employees DWH
pandas_df = employees_dwh.toPandas()
pandas_df.to_csv(r"P:/Career/Data Engineering/ITI-DE/Graduation Project/Data/Data Destinations/Employees.csv", index=False)

# Save Transactions Fact Table
pandas_df = transactions_dwh.toPandas()
pandas_df.to_csv(r"P:/Career/Data Engineering/ITI-DE/Graduation Project/Data/Data Destinations/Transactions1_2.csv", index=False)
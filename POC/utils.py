from flask import session
from flask_login import current_user
import pandas as pd
import azure.cosmos.exceptions as exceptions
import os
import azure.cosmos.cosmos_client as cosmos_client
from dotenv import load_dotenv

load_dotenv()


def get_cosmos_db():
    settings = {
        "host": os.environ.get(
            "ACCOUNT_HOST", "https://emergencycosmos.documents.azure.com:443/"
        ),
        "master_key": os.getenv("COSMOS_KEY"),
        "database_id": os.environ.get("COSMOS_DATABASE", "ReliefApp"),
        "container_id": os.environ.get("COSMOS_CONTAINER", "Beneficiaries"),
    }
    client = cosmos_client.CosmosClient(
        settings["host"],
        {"masterKey": settings["master_key"]},
        user_agent="ReliefApp",
        user_agent_overwrite=True,
    )
    return client.get_database_client(settings["database_id"])


cosmos_db = get_cosmos_db()


def get_local_data_path(user_email, distrib_id):
    data_dir = "instance"
    os.makedirs(data_dir, exist_ok=True)
    return f"{data_dir}/user_{user_email}_distrib_{distrib_id}_data.csv"


def delete_beneficiary_data(user_email, distrib_id):
    if os.getenv("MODE") == "online":
        cosmos_container = cosmos_db.get_container_client("Beneficiaries")
        item_list = query_items_by_partition_key(cosmos_container, user_email)
        item_list = filter_by_distribution(item_list, distrib_id)
        for item in item_list:
            cosmos_container.delete_item(item=item["id"], partition_key=user_email)
    elif os.getenv("MODE") == "offline":
        database = get_local_data_path(user_email, distrib_id)
        if os.path.exists(database):
            os.remove(database)


def get_beneficiary_data(user_email, distrib_id):
    df = pd.DataFrame()

    if os.getenv("MODE") == "online":
        cosmos_container = cosmos_db.get_container_client("Beneficiaries")
        item_list = query_items_by_partition_key(cosmos_container, user_email)
        item_list = filter_by_distribution(item_list, distrib_id)
        df = pd.DataFrame(item_list)
    elif os.getenv("MODE") == "offline":
        database = get_local_data_path(user_email, distrib_id)
        if os.path.exists(database):
            df = pd.read_csv(database, index_col=0, sep=";")
        else:
            return None
    if df.empty:
        return None
    else:
        df = df.drop(columns=["partitionKey", "id", "distrib_id"], errors="ignore")
        df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
        return df


def get_beneficiary_entry(beneficiary_id, user_email, distrib_id):
    if os.getenv("MODE") == "online":
        cosmos_container = cosmos_db.get_container_client("Beneficiaries")
        try:
            data = cosmos_container.read_item(
                item=beneficiary_id, partition_key=user_email
            )
            for internal_field in [k for k in data.keys() if k.startswith("_")]:
                data.pop(internal_field)
            return data
        except exceptions.CosmosResourceNotFoundError:
            return "not_found"
    elif os.getenv("MODE") == "offline":
        database = get_local_data_path(user_email, distrib_id)
        if os.path.exists(database):
            df = pd.read_csv(database, sep=";", dtype={"id": str}).set_index("id")
            if beneficiary_id in df.index:
                return df.loc[beneficiary_id].to_dict()
            else:
                return "not_found"
        else:
            return "no_data"


def update_beneficiary_entry(beneficiary_id, user_email, distrib_id, replace_body):
    if os.getenv("MODE") == "online":
        try:
            cosmos_container = cosmos_db.get_container_client("Beneficiaries")
            read_item = cosmos_container.read_item(
                item=beneficiary_id, partition_key=user_email
            )
            for key in replace_body.keys():
                read_item[key] = replace_body[key]
            cosmos_container.replace_item(item=read_item, body=read_item)
            return "success"
        except exceptions.CosmosResourceNotFoundError:
            return "not_found"
    elif os.getenv("MODE") == "offline":
        database = get_local_data_path(user_email, distrib_id)
        if os.path.exists(database):
            df = pd.read_csv(database, sep=";", dtype={"id": str}).set_index("id")
            if beneficiary_id in df.index:
                for key in replace_body.keys():
                    df.at[beneficiary_id, key] = replace_body[key]
                df.to_csv(database, sep=";")
                return "success"
            else:
                return "not_found"
        else:
            return "no_data"


def save_beneficiary_data(data, distrib_id, user_email):
    data_to_save = []
    for ix, row in data.iterrows():
        body = {
            "id": str(distrib_id) + str(row["code"]),
            "partitionKey": user_email,
            "distrib_id": str(distrib_id),
        }
        for key in row.keys():
            if key != "id" and key != "partitionKey" and key != "distrib_id":
                body[key] = str(row[key])
        data_to_save.append(body)

    print(data_to_save)

    if os.getenv("MODE") == "online":
        cosmos_container = cosmos_db.get_container_client("Beneficiaries")
        # save to cosmos db
        for entry in data_to_save:
            cosmos_container.create_item(body=entry)
    elif os.getenv("MODE") == "offline":
        database = get_local_data_path(user_email, distrib_id)
        df = pd.DataFrame.from_records(data_to_save)
        df.index = df["id"]
        df = df.drop(columns=["id"])
        df.to_csv(database, sep=";")


def query_items_by_partition_key(container, key):
    # Including the partition key value of account_number in the WHERE filter results in a more efficient query
    items = list(
        container.query_items(
            query="SELECT * FROM r WHERE r.partitionKey=@key",
            parameters=[{"name": "@key", "value": key}],
        )
    )
    return items


def filter_by_distribution(item_list, distrib_id):
    for item in item_list[:]:
        if "distrib_id" in item.keys():
            if str(item["distrib_id"]) != str(distrib_id):
                item_list.remove(item)
    return item_list


def pandas_to_html(df, replace_values={}, replace_columns={}, titlecase=False):
    df = df.replace(replace_values)
    df = df.rename(columns=replace_columns)
    if titlecase:
        df.columns = [x.title() for x in df.columns]
    columns = list(df.columns)
    rows = []
    print(df)
    for ix, row in df.iterrows():
        row_dict = row.to_dict()
        for key in row.keys():
            row[key] = str(row[key]).strip()
        rows.append(row_dict)
    print(columns, rows)
    return columns, rows


def save_single_beneficiary(beneficiary_data, distrib_id, user_email):
    """Save a single beneficiary record to the database with comprehensive error handling."""
    try:
        # Validate input parameters
        if not beneficiary_data:
            raise ValueError("beneficiary_data cannot be empty")
        if not distrib_id:
            raise ValueError("distrib_id cannot be empty")
        if not user_email:
            raise ValueError("user_email cannot be empty")
        if "code" not in beneficiary_data:
            raise ValueError("beneficiary_data must contain 'code' field")

        # Create the body for the beneficiary record
        body = {
            "id": str(distrib_id) + str(beneficiary_data["code"]),
            "partitionKey": user_email,
            "distrib_id": str(distrib_id),
        }

        # Add all other fields from the beneficiary data
        for key in beneficiary_data.keys():
            if key not in ["id", "partitionKey", "distrib_id"]:
                body[key] = str(beneficiary_data[key]) if beneficiary_data[key] is not None else ""

        # Determine storage mode
        mode = os.getenv("MODE", "offline")
        
        if mode == "online":
            try:
                cosmos_container = cosmos_db.get_container_client("Beneficiaries")
                # Save to cosmos db
                result = cosmos_container.create_item(body=body)
                if not result:
                    raise Exception("Failed to create item in Cosmos DB - no result returned")
            except Exception as e:
                raise Exception(f"Failed to save to Cosmos DB: {str(e)}")
                
        elif mode == "offline":
            try:
                database = get_local_data_path(user_email, distrib_id)
                
                # Ensure the directory exists
                os.makedirs(os.path.dirname(database), exist_ok=True)
                
                # Load existing data or create new DataFrame
                if os.path.exists(database):
                    try:
                        existing_df = pd.read_csv(database, sep=";", dtype={"id": str}).set_index("id")
                        # Check if beneficiary already exists
                        if body["id"] in existing_df.index:
                            raise ValueError(f"Beneficiary with ID {body['id']} already exists")
                        # Add new record
                        for key, value in body.items():
                            existing_df.at[body["id"], key] = value
                    except pd.errors.EmptyDataError:
                        # File exists but is empty, create new DataFrame
                        existing_df = pd.DataFrame([body]).set_index("id")
                    except Exception as e:
                        raise Exception(f"Failed to read existing data file: {str(e)}")
                else:
                    # Create new DataFrame with the single record
                    existing_df = pd.DataFrame([body]).set_index("id")

                # Save to CSV
                try:
                    existing_df.to_csv(database, sep=";")
                    # Verify the file was written
                    if not os.path.exists(database):
                        raise Exception("File was not created successfully")
                except Exception as e:
                    raise Exception(f"Failed to write to CSV file: {str(e)}")
                    
            except Exception as e:
                raise Exception(f"Failed to save to local database: {str(e)}")
        else:
            raise ValueError(f"Invalid MODE setting: {mode}. Must be 'online' or 'offline'")

        return body["id"]
        
    except Exception as e:
        # Log the error and re-raise with more context
        import logging
        logging.error(f"Error in save_single_beneficiary: {str(e)}")
        raise Exception(f"Failed to save beneficiary: {str(e)}")

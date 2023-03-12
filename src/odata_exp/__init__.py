import secrets
from datetime import date
from typing import Dict, List, Optional

from fastapi import FastAPI, Response, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from inflect import engine as inflect_engine
from jinja2 import Environment as JinjaEnvironment, PackageLoader
from psycopg2 import connect as pg_connect, sql
from psycopg2.extras import DictCursor
from shapely import wkb, Point
from starlette import status

app = FastAPI()
security = HTTPBasic(realm="OData Experiments")
templates = JinjaEnvironment(loader=PackageLoader("odata_exp"))

config = {
    "namespace": "ODataExperiments",
    "endpoint": "http://localhost:8004",
    "auth": {"username": "conwat", "password": "password"},
    "db_dsn": "host=localhost dbname=odata_exp user=odata_exp",
}

inflection = inflect_engine()


def format_column_name(column_name: str) -> str:
    if column_name == "id":
        return "ID"

    return column_name.replace("_", " ").title()


def reverse_format_column_name(column_name: str) -> str:
    if column_name == "ID":
        return "id"

    return column_name.replace(" ", "_").lower()


def determine_column_type(column_type: str) -> str:
    if column_type == "text":
        return "Edm.String"
    elif column_type == "integer":
        return "Edm.Int32"
    elif column_type == "date":
        return "Edm.Date"


def check_auth(credentials: HTTPBasicCredentials) -> None:
    auth_username = config["auth"]["username"].encode()
    auth_password = config["auth"]["password"].encode()

    login_username = credentials.username.encode()
    login_password = credentials.password.encode()

    if not secrets.compare_digest(login_username, auth_username) or not secrets.compare_digest(
        login_password, auth_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )


def list_table_names() -> List[str]:
    table_names = []

    connection = pg_connect(dsn=config["db_dsn"])
    cursor = connection.cursor(cursor_factory=DictCursor)
    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND
              table_name NOT IN ('spatial_ref_sys', 'geography_columns', 'geometry_columns');
        """
    )
    for table in cursor.fetchall():
        table_names.append(table[0])
    connection.close()

    return table_names


def list_table_columns() -> Dict[str, List[Dict[str, str]]]:
    table_columns = {}

    connection = pg_connect(dsn=config["db_dsn"])
    cursor = connection.cursor(cursor_factory=DictCursor)

    cursor.execute(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND
              table_name NOT IN ('spatial_ref_sys', 'geography_columns', 'geometry_columns')
        ORDER BY ordinal_position;
        """
    )
    for column in cursor.fetchall():
        if column[0] not in table_columns.keys():
            table_columns[column[0]] = []

        table_columns[column[0]].append({"name": column[1], "type": column[2]})

    cursor.execute(
        """
        SELECT f_table_name, f_geometry_column, type
        FROM public.geometry_columns;
        """
    )
    for geom_column in cursor.fetchall():
        for table_name, columns in table_columns.items():
            for i, column in enumerate(columns):
                if geom_column[0] == table_name and geom_column[1] == column["name"]:
                    table_columns[table_name][i]["type"] = "geometry"
                    table_columns[table_name][i]["geometry_type"] = geom_column[2]

    cursor.execute(
        """
        SELECT tc.table_name, ccu.column_name, tc.constraint_type
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage AS ccu USING (constraint_schema, constraint_name)
        WHERE tc.table_schema = 'public' AND tc.constraint_type = 'PRIMARY KEY';
        """
    )
    for pk_column in cursor.fetchall():
        for table_name, columns in table_columns.items():
            for i, column in enumerate(columns):
                if pk_column[0] == table_name and pk_column[1] == column["name"]:
                    table_columns[table_name][i]["pk"] = True

    connection.close()

    return table_columns


def get_entities() -> List[dict]:
    entities = []

    for table_name, columns in list_table_columns().items():
        entity = {
            "name": table_name.capitalize(),
            "collection": inflection.plural(table_name).capitalize(),
            "properties": [],
        }

        for column in columns:
            if column["type"] == "geometry" and "geometry_type" in column and column["geometry_type"] == "POINT":
                latitude = {"name": "Latitude", "type": "Edm.Decimal"}
                longitude = {"name": "Longitude", "type": "Edm.Decimal"}
                entity["properties"].append(latitude)
                entity["properties"].append(longitude)
                continue

            property_ = {
                "name": format_column_name(column_name=column["name"]),
                "type": determine_column_type(column_type=column["type"]),
            }
            if "pk" in column and column["pk"]:
                property_["is_key"] = True

            entity["properties"].append(property_)

        entities.append(entity)

    return entities


def get_entity(entity_collection: str = None) -> Optional[dict]:
    for entity_definition_ in get_entities():
        if entity_definition_["collection"] == entity_collection:
            return entity_definition_

    return None


def get_entity_key_property(entity_definition: dict) -> str:
    for property_ in entity_definition["properties"]:
        if "is_key" in property_ and property_["is_key"]:
            return property_["name"]


def has_geometry_properties(entity_definition: dict) -> bool:
    property_names = []
    for property_ in entity_definition["properties"]:
        property_names.append(property_["name"])

    if "Latitude" in property_names and "Longitude" in property_names:
        return True

    return False


@app.get("/")
def root():
    payload = {"@odata.context": f"{config['endpoint']}/$metadata", "value": []}

    for entity in get_entities():
        payload["value"].append(
            {
                "name": entity["collection"],
                "kind": "EntitySet",
                "url": f"{config['endpoint']}/{entity['collection']}",
            }
        )

    return JSONResponse(
        content=payload,
        status_code=status.HTTP_200_OK,
        headers={
            "Content-Type": "application/json; odata.metadata=minimal; odata.streaming=false",
            "OData-Version": "4.0",
        },
    )


@app.get("/$metadata")
def metadata():
    template = templates.get_template("odata-metadata.j2.xml")
    payload = template.render(namespace=config["namespace"], entities=get_entities())

    return Response(
        content=payload,
        status_code=status.HTTP_200_OK,
        media_type="application/xml",
        headers={"OData-Version": "4.0"},
    )


@app.get("/{entity_collection}")
def depots(entity_collection: str, credentials: HTTPBasicCredentials = Depends(security)):
    check_auth(credentials=credentials)

    table_name = inflection.singular_noun(entity_collection).lower()
    if table_name not in list_table_names():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown table.")

    entity_definition = get_entity(entity_collection=entity_collection)
    if entity_definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown entity definition.")

    key_column_name = get_entity_key_property(entity_definition=entity_definition)
    geometry_properties = has_geometry_properties(entity_definition=entity_definition)

    payload = {"@odata.context": f"{config['endpoint']}/$metadata#{entity_collection}", "value": []}

    connection = pg_connect(dsn=config["db_dsn"])
    cursor = connection.cursor(cursor_factory=DictCursor)
    query = (
        sql.SQL("""SELECT * FROM {} ORDER BY {};""")
        .format(sql.Identifier(table_name), sql.Identifier(reverse_format_column_name(column_name=key_column_name)))
        .as_string(cursor)
    )
    cursor.execute(query)
    for row in cursor.fetchall():
        entity = {}
        for i, column in enumerate(row):
            column_name = format_column_name(column_name=cursor.description[i].name)

            if isinstance(column, date):
                column = column.isoformat()

            if column_name == key_column_name:
                entity["@odata.id"] = f"{config['endpoint']}/{entity_collection}('{column}')"

            if column_name == "Geom" and geometry_properties:
                geom: Point = wkb.loads(column)
                entity["Latitude"] = geom.y
                entity["Longitude"] = geom.x
                continue

            entity[column_name] = column

        payload["value"].append(entity)
    connection.close()

    return JSONResponse(
        content=payload,
        status_code=status.HTTP_200_OK,
        headers={
            "Content-Type": "application/json; odata.metadata=minimal; odata.streaming=false",
            "OData-Version": "4.0",
        },
    )

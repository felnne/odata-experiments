import secrets

from fastapi import FastAPI, Response, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jinja2 import Environment as JinjaEnvironment, PackageLoader
from starlette import status

from odata_exp.data import get_depots

security = HTTPBasic(realm="OData Experiments")

app = FastAPI()

templates = JinjaEnvironment(loader=PackageLoader("odata_exp"))

config = {
    "namespace": "ODataExperiments",
    "endpoint": "http://localhost:8004",
    "entities": [
        {
            "name": "Depot",
            "collection": "Depots",
            "properties": [
                {
                    "name": "Identifier",
                    "type": "Edm.String",
                    "is_key": True,
                    "nullable": False,
                },
                {
                    "name": "Latitude",
                    "type": "Edm.Decimal",
                    "is_key": False,
                    "nullable": False,
                },
                {
                    "name": "Longitude",
                    "type": "Edm.Decimal",
                    "is_key": False,
                    "nullable": False,
                },
                {
                    "name": "Date Established",
                    "type": "Edm.Date",
                    "is_key": False,
                    "nullable": True,
                },
            ],
        }
    ],
    "auth": {"username": "conwat", "password": "password"},
}


def check_auth(credentials: HTTPBasicCredentials):
    auth_username = config["auth"]["username"].encode()
    auth_password = config["auth"]["password"].encode()

    login_username = credentials.username.encode()
    login_password = credentials.password.encode()

    if not secrets.compare_digest(
        login_username, auth_username
    ) or not secrets.compare_digest(login_password, auth_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )


@app.get("/")
def root():
    payload = {"@odata.context": f"{config['endpoint']}/$metadata", "value": []}

    for entity in config["entities"]:
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
    payload = template.render(context=config)

    return Response(
        content=payload,
        status_code=status.HTTP_200_OK,
        media_type="application/xml",
        headers={"OData-Version": "4.0"},
    )


@app.get("/Depots")
def depots(credentials: HTTPBasicCredentials = Depends(security)):
    check_auth(credentials=credentials)

    payload = {"@odata.context": f"{config['endpoint']}/$metadata#Depots", "value": []}

    for depot in get_depots():
        payload["value"].append(
            {
                "@odata.id": f"{config['endpoint']}/Depots('{depot['identifier']}')",
                "Identifier": depot["identifier"],
                "Latitude": depot["latitude"],
                "Longitude": depot["longitude"],
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

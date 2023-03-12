# OData Experiments

Experiment to create a minimal, authenticated, OData server for loading data into Excel.

## Aim

This experiment looks at whether it's possible access information from a GIS within an Excel without creating 
periodic exports (which can get out of date and run the risk of fragmenting information). Specifically it looks at 
whether we could use the [OData](https://www.odata.org) standard as an interface between the GIS and Excel. 

## Rational

MAGIC are providing a GIS for Field Operations to assist with their data management. During discovery, we learnt that
Field Operations use Excel to perform ad-hoc analysis of their information.

## Limitations

1. ~~static data~~
2. ~~static authentication~~
3. ~~data schema changes require app restart~~
4. we only support point geometry columns (minor, won't be addressed)
5. hyperlink fields are not supported in OData:
    * a `HYPERLINK()` formula can be given but isn't interpreted when loaded
    * link columns in a SharePoint list don't work either
    * [possible solution on Windows?](https://community.powerbi.com/t5/Desktop/Hyperlink-in-Power-Query-Editor/m-p/140333/highlight/true#M60427)
    * [workaround using Excel Script](https://nercacuk-my.sharepoint.com/:u:/r/personal/felnne_bas_ac_uk/Documents/Apps/Microsoft%20Excel/Scripts/Add%20Hyperlinks%20from%20Sheet.osts?csf=1&web=1&e=cCoyvA)
6. Excel has extremely aggressive caching:
    * [possible solution on Windows?](https://community.powerbi.com/t5/Power-Query/Excel-Power-Query-Cache-Folder/m-p/2638525/highlight/true#M80795)
7. LDAP group information not checked (minor as read only)

## Usage

Start LDAP server:

```
./ldap/glauth -c ./ldap/config.cfg
```

Start app server:

```shell
$ poetry run uvicorn odata_exp:app --port 8004
```

Then from Excel:

* create a Power Query 
  [OData connection](https://support.microsoft.com/en-us/office/be4330b3-5356-486c-a168-b68e9e616f5a)
* enter `http://localhost:8004` as the OData feed URL
* set the authentication type to *basic*
* set the username to `conwat`
* set the password to `password`
* select the tables you wish to load
* selected tables are loaded as worksheets within the workbook

Once loaded, imported data can be updated to reflect changes made outside of Excel:

* click within a loaded table
* from the *Table* tab on the ribbon, click the *Refresh* option

**Note:** Any changes made to loaded data are local within the workbook. Edits are written back centrally.

## Implementation

### Available options

OData is one of [several options](https://support.microsoft.com/en-us/office/be4330b3-5356-486c-a168-b68e9e616f5a) 
Excel supports to access information from other systems. Others include:

- SharePoint
- other SaaS services (inc. SalesForce)
- direct database connections (inc. Postgres)

Reviewing these:

- SharePoint is used by Field Operations to manage information in Cambridge but is not viable to use on station
- Other SaaS services aren't used but would also be similarly infeasible South.
- direct database connections require drivers to be installed on each client machine and expose internal technology
  choices to end users, potentially limiting our ability to change technologies in future

In contrast, OData:

- is the underlying interface used by SharePoint, and is used across other Microsoft products
- built into Excel, without the need for drivers
- provides an abstraction/interface between end-users and specific technologies

### OData implementations

This experiment will look at:

- which elements of the OData standard are required to load data in Excel
- whether these can be easily implemented in Python (i.e. with an existing library or 1-4 hours effort)
- if not, whether there is a library/solution in another language that could be practically used instead

This experiment will *not*:

- seek to create a full server implementation, or even one that meets the minimum requirements of the OData standard
- follow any best practices or performance guidelines

Having reviewed some existing server implementations:

- there does not appear to be a simple, off the shelf, options for Python
- There are frameworks in C#, which look relatively straightforward to implement but would be complex to deploy South
- a framework in PHP would be more suitable but would effectively create a parallel application

With no ideal solution identified, and existing options implementing the full OData standard, which we don't need, I 
opted to see if a much more minimal, bare-bones implementation could be created in Python (with 1-4 hours of effort). 

### Reverse engineering

Using the OData sample/reference service, I wanted to see if I could replicate the content of the endpoints Excel 
probably uses, and if successful, experiment in adapting this to work with custom data/types that superficially
resembles data that would be held in the GIS.

References:

* https://services.odata.org/TripPinRESTierService/(S(zpbxinreiwjcykwiwzheu5fx))/$metadata#People
* https://www.odata.org/getting-started/basic-tutorial/#queryData

Using these it was straightforward to replicate an index endpoint and a table (in JSON) and attempt to create a 
metadata document (in XML) using FastAPI. This worked in getting a list of tables to show in Excel but took more time
to configure the metadata document correctly. After several iterations it did then work and data came through as 
expected.

I then experimented with adding basic authentication to the table endpoint (such that the index and metadata endpoints
were unprotected). This worked on the first try.

### Entities

Entities in OData represent datasets or tables (e.g. Depots, People or Orders). Entities represent single instances of 
a thing, collections are used for multiple instances. Entities, and collections they appear within, are defined in the
OData metadata document.

To reflect real world usage, where Field Operations will create new datasets at will, this experiment introspects
available tables in a Postgres database on each request (to avoid app restarts on schema changes).

A single *Depot* entity, representing a simple form of a depot is provided by default. Other entities can be added as 
desired.

### Primitive types

OData entities include a number of properties, which represent attributes or columns within datasets or tables (e.g. 
ID, Name, Latitude/Longitude, Last Accessed At). These properties, including a data type, are outputted in the OData
metadata document. Valid data types are 
[listed](https://docs.oasis-open.org/odata/odata-csdl-json/v4.01/odata-csdl-json-v4.01.html#sec_PrimitiveTypes) in the 
OData standard and utilise the type system present in XML, including simple and complex types.

For our needs, only simple or primitive types are needed (e.g. string, integer, datetime, etc.) and are used by Excel
to set the correct column type.

Notably, these OData types include geospatial types (geographic and geometry), however I don't think these are needed 
as they can't be used in Excel in a useful way.

To reflect real world usage, where Field Operations will create or amend attributes within datasets at will, this 
experiment introspects columns within Postgres tables on each request (to avoid app restarts on schema changes).

### Endpoints

Three endpoints are needed to load data into Excel:

1. entrypoint - root of service, providing a list of entities and link to metadata document
2. metadata - metadata document defining entities, their properties and the collections they appear in
3. entities - per-entity/collection endpoints that list entities within a collection (i.e. contents of a table)

### Endpoint examples

**Note:** These are minimal examples and don't reflect the state of the current service.

Entrypoint:

```shell
$ curl http://localhost:8004/
```

```json
{
  "@odata.context": "http://localhost:8004/$metadata",
  "value": [
    {
      "name": "Depots",
      "kind": "EntitySet",
      "url": "http://localhost:8004/Depots"
    }
  ]
}
```

Metadata:

```shell
$ curl http://localhost:8004/$metadata
```

```xml
<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">
  <edmx:DataServices>
    <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="ODataExperiments">
      <EntityType Name="Depot">
        <Key>
          <PropertyRef Name="Identifier"/>
        </Key>
        <Property Name="Identifier" Type="Edm.String" Nullable="False"/>
        <Property Name="Latitude" Type="Edm.Decimal" Nullable="False"/>
        <Property Name="Longitude" Type="Edm.Decimal" Nullable="False"/>
      </EntityType>
      <EntityContainer Name="Container">
        <EntitySet Name="Depots" EntityType="ODataExperiments.Depot"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
```

Entity:

```shell
$ curl http://localhost:8004/Depots
```

```json
{
  "@odata.context": "http://localhost:8004/$metadata#Depots",
  "value": [
    {
      "@odata.id": "http://localhost:8004/Depots('Alpha')",
      "Identifier": "Alpha",
      "Latitude": -69.46861,
      "Longitude": -72.079415
    },
    {
      "@odata.id": "http://localhost:8004/Depots('Bravo')",
      "Identifier": "Bravo",
      "Latitude": -69.233975,
      "Longitude": -72.336723
    },
    {
      "@odata.id": "http://localhost:8004/Depots('Charlie')",
      "Identifier": "Charlie",
      "Latitude": -68.956924,
      "Longitude": -72.42049
    }
  ]
}
```

### Authentication

To mimic real world usage, where LDAP will be used for centralised authentication, a local LDAP server is used. This is
configured with statically defined users, however from the perspective of the application, it is performing a dynamic
check on credentials for restricted routes.

Users are other LDAP server configuration is set in `./ldap/config.cfg`.

## Development

### Development requirements

* PostgreSQL with PostGIS extension
* Python 3.11 (pyenv recommended)
* Poetry
* Git
* [glauth](https://github.com/glauth/glauth)

### Development setup

#### Setup python environment

```shell
$ git clone ...
$ cd odata-exp

# if using pyenv set to Python 3.11
$ pyenv local 3.11.x

$ poetry install
```

#### Setup LDAP

Download the latest [glauth release](https://github.com/glauth/glauth/releases) binary to `./ldap`. 

#### Setup PostgreSQL

Create database:

```shell
$ psql -c 'create database odata_exp;'
$ psql -c 'create role odata_exp;'
$ psql -c 'grant all privileges on odata_exp;'
$ psql -d odata_exp -c 'grant all privileges on all tables in schema public to odata_exp'
```

Populate database:

```sql
create extension postgis;

create table depot
(
    id  
        integer generated always as identity
        constraint depots_pk primary key,
    identifier 
        text not null
        constraint depots_uq_identifier unique,
    established_at 
        date,
    geom
        geometry(Point, 4326) not null
);

INSERT INTO depot (identifier, established_at, geom) VALUES ('Alpha', '2018-11-04', '0101000020E61000000DCF3421150552C00BE50EB5FD5D51C0');
INSERT INTO depot (identifier, established_at, geom) VALUES ('Bravo', '2023-03-11', '0101000020E6100000064542E08C1552C06761F672F94E51C0');
INSERT INTO depot (identifier, established_at, geom) VALUES ('Charlie', '2016-10-16', '0101000020E61000005A21C44EE91A52C01168533E3E3D51C0');
INSERT INTO depot (identifier, established_at, geom) VALUES ('Delta', '2020-10-05', '0101000020E61000005AD6753A87E651C03AADE61B6B2D51C0');
INSERT INTO depot (identifier, established_at, geom) VALUES ('Echo', '2022-02-24', '0101000020E61000000F59BB58F4D351C0EC9A291EC21351C0');
```

### LDAP

To verify LDAP is working correctly use `ldapsearch`, which should return output similar to this:

```shell
$ ldapsearch -LLL -H ldap://localhost:3893 -D cn=conwat,ou=staff,dc=felnne,dc=net -w password -x -bdc=felnne,dc=net cn=conwat
dn: cn=conwat,ou=staff,ou=users,dc=felnne,dc=net
cn: conwat
uid: conwat
givenName: Connie
sn: Watson
ou: staff
uidNumber: 5001
accountStatus: active
mail: conwat@bas.ac.uk
userPrincipalName: conwat@bas.ac.uk
objectClass: posixAccount
objectClass: shadowAccount
loginShell: /bin/bash
homeDirectory: /home/conwat
description: conwat
gecos: conwat
gidNumber: 5501
memberOf: ou=staff,ou=groups,dc=felnne,dc=net
shadowExpire: -1
shadowFlag: 134538308
shadowInactive: -1
shadowLastChange: 11000
shadowMax: 99999
shadowMin: -1
shadowWarning: 7
```

## License

Copyright (c) 2023 UK Research and Innovation (UKRI), British Antarctic Survey.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

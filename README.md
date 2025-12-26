# Backend for Verve Outdoors


## Dependencies

- A postgrSQL instance with enables postgis extension
- Some kind of boto3 compatible object store (e.g. minio)

## Database setup

Create a user for the *RLS policies* on you database instance

```sql
CREATE ROLE verve_user LOGIN PASSWORD 'changeme' NOINHERIT;
```

Initialze the database using *alembic*

```bash
alembic upgrade head
```

This also create the relvant schema and *initializes the RLS policy for the tables*.

You can verify the *RLS policies* with the script `./scripts/verify_rls.py`


### Notes on the RLS setup

- Create a role for RLS: `CREATE ROLE verve_user LOGIN PASSWORD 'changeme' NOINHERIT;`
- Grand usage on schema: `GRANT USAGE ON SCHEMA verve TO verve_user;`
- Set privileges:

```sql
ALTER DEFAULT PRIVILEGES IN SCHEMA verve GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO verve_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA verve GRANT USAGE ON SEQUENCES TO verve_user;
```

RLS (Row-Level Security) is enabled as follows:

```sql
ALTER TABLE verve.activities ENABLE ROW LEVEL SECURITY;
CREATE POLICY activity_isolation_policy ON verve.activities
    FOR ALL USING (user_id = current_setting('verve_user.curr_user')::uuid);
```

and in the beginning of the db session something like this has to be done (when using the `verve_user` role for connecting)

```sql
SET verve_user.curr_user = '{user.id}'`
```




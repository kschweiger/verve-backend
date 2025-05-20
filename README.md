# Backend for Verve Outdoors

## Database setup

Assuming you have working POSTGRES instance ready:

- Create a schema: `CREATE SCHEMA verve;`
- Create a role for RLS: `CREATE ROLE verve_user LOGIN PASSWORD 'changeme' NOINHERIT;`
- Grand usage on schema: `GRANT USAGE ON SCHEMA verve TO verve_user;`
- Set privileges: `ALTER DEFAULT PRIVILEGES IN SCHEMA verve GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO verve_user;`

RLS (Row-Level Security) is enabled as follows:

```sql
ALTER TABLE verve.activities ENABLE ROW LEVEL SECURITY;
CREATE POLICY activity_isolation_policy ON verve.activities
    FOR ALL USING (user_id = current_setting('verve_user.curr_user')::uuid);
```

and in the beginning of the db session something like this has to be done (when using the `verve_user` role for connecting)

```
```sql
SET verve_user.curr_user = '{user.id}'`
```

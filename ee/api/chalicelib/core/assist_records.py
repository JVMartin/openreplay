import hashlib

from decouple import config

import schemas
import schemas_ee
from chalicelib.utils import s3, pg_client, helper, s3_extra
from chalicelib.utils.TimeUTC import TimeUTC


def generate_file_key(project_id, key):
    return f"{project_id}/{hashlib.md5(key.encode()).hexdigest()}"


def presign_record(project_id, data: schemas_ee.AssistRecordPayloadSchema, context: schemas_ee.CurrentContext):
    key = generate_file_key(project_id=project_id, key=f"{TimeUTC.now()}-{data.name}")
    presigned_url = s3.get_presigned_url_for_upload(bucket=config('ASSIST_RECORDS_BUCKET'), expires_in=1800, key=key)
    return {"URL": presigned_url, "key": key}


def save_record(project_id, data: schemas_ee.AssistRecordSavePayloadSchema, context: schemas_ee.CurrentContext):
    s3_extra.tag_record(file_key=data.key, tag_value=config('RETENTION_L_VALUE', default='vault'))
    params = {"user_id": context.user_id, "project_id": project_id, **data.dict()}
    with pg_client.PostgresClient() as cur:
        query = cur.mogrify(
            f"""INSERT INTO assist_records(project_id, user_id, name, file_key, duration, session_id)
                VALUES (%(project_id)s, %(user_id)s, %(name)s, %(key)s,%(duration)s, %(session_id)s)
                RETURNING record_id, user_id, session_id, created_at, name, duration, 
                        (SELECT name FROM users WHERE users.user_id = %(user_id)s LIMIT 1) AS created_by, file_key;""",
            params)
        cur.execute(query)
        result = helper.dict_to_camel_case(cur.fetchone())
        result["URL"] = s3.client.generate_presigned_url(
            'get_object',
            Params={'Bucket': config("ASSIST_RECORDS_BUCKET"), 'Key': result.pop("fileKey")},
            ExpiresIn=config("PRESIGNED_URL_EXPIRATION", cast=int, default=900)
        )
    return result


def search_records(project_id, data: schemas_ee.AssistRecordSearchPayloadSchema, context: schemas_ee.CurrentContext):
    conditions = ["projects.tenant_id=%(tenant_id)s",
                  "projects.deleted_at ISNULL",
                  "assist_records.created_at>=%(startDate)s",
                  "assist_records.created_at<=%(endDate)s",
                  "assist_records.deleted_at ISNULL"]
    params = {"tenant_id": context.tenant_id, "project_id": project_id,
              "startDate": data.startDate, "endDate": data.endDate,
              "p_start": (data.page - 1) * data.limit, "p_limit": data.limit,
              **data.dict()}
    if data.user_id is not None:
        conditions.append("assist_records.user_id=%(user_id)s")
    if data.query is not None and len(data.query) > 0:
        conditions.append("(users.name ILIKE %(query)s OR assist_records.name ILIKE %(query)s)")
        params["query"] = helper.values_for_operator(value=data.query,
                                                     op=schemas.SearchEventOperator._contains)
    with pg_client.PostgresClient() as cur:
        query = cur.mogrify(f"""SELECT record_id, user_id, session_id, assist_records.created_at, 
                                        assist_records.name, duration, users.name AS created_by
                                FROM assist_records
                                         INNER JOIN projects USING (project_id)
                                         LEFT JOIN users USING (user_id)
                                WHERE {" AND ".join(conditions)}
                                ORDER BY assist_records.created_at {data.order}
                                LIMIT %(p_limit)s OFFSET %(p_start)s;""",
                            params)
        cur.execute(query)
        results = helper.list_to_camel_case(cur.fetchall())
    return results


def get_record(project_id, record_id, context: schemas_ee.CurrentContext):
    conditions = ["projects.tenant_id=%(tenant_id)s",
                  "projects.deleted_at ISNULL",
                  "assist_records.record_id=%(record_id)s",
                  "assist_records.deleted_at ISNULL"]
    params = {"tenant_id": context.tenant_id, "project_id": project_id, "record_id": record_id}
    with pg_client.PostgresClient() as cur:
        query = cur.mogrify(f"""SELECT record_id, user_id, session_id, assist_records.created_at, 
                                       assist_records.name, duration, users.name AS created_by,
                                       file_key
                                FROM assist_records
                                         INNER JOIN projects USING (project_id)
                                         LEFT JOIN users USING (user_id)
                                WHERE {" AND ".join(conditions)}
                                LIMIT 1;""", params)
        cur.execute(query)
        result = helper.dict_to_camel_case(cur.fetchone())
        if result:
            result["URL"] = s3.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': config("ASSIST_RECORDS_BUCKET"), 'Key': result.pop("fileKey")},
                ExpiresIn=config("PRESIGNED_URL_EXPIRATION", cast=int, default=900)
            )
    return result


def update_record(project_id, record_id, data: schemas_ee.AssistRecordUpdatePayloadSchema,
                  context: schemas_ee.CurrentContext):
    conditions = ["assist_records.record_id=%(record_id)s", "assist_records.deleted_at ISNULL"]
    params = {"tenant_id": context.tenant_id, "project_id": project_id, "record_id": record_id, "name": data.name}
    with pg_client.PostgresClient() as cur:
        query = cur.mogrify(f"""UPDATE assist_records
                                SET name= %(name)s
                                FROM (SELECT users.name AS created_by
                                      FROM assist_records INNER JOIN users USING (user_id)
                                      WHERE record_id = %(record_id)s
                                        AND assist_records.deleted_at ISNULL
                                      LIMIT 1) AS users
                                WHERE {" AND ".join(conditions)}
                                RETURNING record_id, user_id, session_id, assist_records.created_at, 
                                       assist_records.name, duration, created_by, file_key;""", params)
        cur.execute(query)
        result = helper.dict_to_camel_case(cur.fetchone())
        if not result:
            return {"errors": ["record not found"]}
        result["URL"] = s3.client.generate_presigned_url(
            'get_object',
            Params={'Bucket': config("ASSIST_RECORDS_BUCKET"), 'Key': result.pop("fileKey")},
            ExpiresIn=config("PRESIGNED_URL_EXPIRATION", cast=int, default=900)
        )
    return result


def delete_record(project_id, record_id, context: schemas_ee.CurrentContext):
    conditions = ["assist_records.record_id=%(record_id)s"]
    params = {"tenant_id": context.tenant_id, "project_id": project_id, "record_id": record_id}
    with pg_client.PostgresClient() as cur:
        query = cur.mogrify(f"""UPDATE assist_records
                                SET deleted_at= (now() at time zone 'utc')
                                WHERE {" AND ".join(conditions)}
                                RETURNING file_key;""", params)
        cur.execute(query)
        result = helper.dict_to_camel_case(cur.fetchone())
        if not result:
            return {"errors": ["record not found"]}
        s3_extra.tag_record(file_key=result["fileKey"], tag_value=config('RETENTION_D_VALUE', default='default'))
    return {"state": "success"}

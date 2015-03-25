-- All trac attachments to link to 
copy
(select
    id, 
    filename, 
    time / 1000000 as PosixTime,
    author 
from
    attachment
order
    by id asc)
to '/tmp/attachments.csv'
with CSV

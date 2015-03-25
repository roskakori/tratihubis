-- All Trac tickets to convert.
copy 
(select
    id,
    type,
    owner,
    reporter,
    milestone,
    status,
    resolution,
    summary,
    description,
    time / 1000000 as PosixTime,
    changetime / 1000000 as ModifiedTime,
    component
from
    ticket
order
    by id)
to '/tmp/tickets.csv'
with CSV

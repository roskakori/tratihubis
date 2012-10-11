-- All Trac tickets to convert.
select
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
    modified / 1000000 as ModifiedTime
from
    ticket
order
    by id

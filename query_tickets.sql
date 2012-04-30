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
    description
from
    ticket
order
    by id

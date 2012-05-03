-- All Trac ticket comments to convert.
select
    ticket,
    time,
    author,
    newvalue
from
    ticket_change
where
    field = 'comment'
    and newvalue <> ''
order
    by ticket, time

-- All Trac ticket comments to convert.
select
    ticket,
    time / 1000000 as PosixTime,
    author,
    newvalue
from
    ticket_change
where
    field = 'comment'
    and newvalue <> ''
order
    by ticket, time

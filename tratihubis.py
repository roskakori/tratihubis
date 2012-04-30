"""
Tool to convert Trac tickets to Github issues.
"""
import codecs
import csv
import github
import logging
import os

_log = logging.getLogger('tratihubis')


class UTF8Recoder:
    """
    Iterator that reads an encoded stream and reencodes the input to UTF-8
    """
    def __init__(self, f, encoding):
        self.reader = codecs.getreader(encoding)(f)

    def __iter__(self):
        return self

    def next(self):  # @ReservedAssignment
        result = self.reader.next().encode("utf-8")
        return result


class UnicodeCsvReader:
    """
    A CSV reader which will iterate over lines in the CSV file "f",
    which is encoded in the given encoding.
    """
    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        f = UTF8Recoder(f, encoding)
        self.reader = csv.reader(f, dialect=dialect, **kwds)

    def next(self):  # @ReservedAssignment
        row = self.reader.next()
        return [unicode(s, "utf-8") for s in row]

    def __iter__(self):
        return self


def _githubLogin():
    result = {'password': None, 'user': None}
    with open(os.path.expandvars('${HOME}/.gitconfig'), 'rb') as configFile:
        for line in configFile:
            line = line.strip('\n\r\t ')
            for keyword in result.keys():
                if line.startswith(keyword + " = "):
                    result[keyword] = line[len(keyword) + 3:]
    return result['user'], result['password']


def _tracTicketMaps():
    """
    Trac tickets read from a CSV file exported from Trac. To export this file, create a Trac ticket query
    using the following statement and click "Download in other formats: Comma-delimited Text" on the result
    page:

    select
        id,
        type,
        time,
        changetime,
        component,
        severity,
        priority,
        owner,
        reporter,
        -- cc,
        version,
        milestone,
        status,
        resolution,
        summary,
        description
        -- keywords
    from
        ticket
    order
        by id
    """
    with open(os.path.expandvars("${HOME}/Desktop/cutplace_trac_tickets.csv"), "rb") as  ticketCsvFile:
        csvReader = UnicodeCsvReader(ticketCsvFile)
        hasReadHeader = False
        for row in csvReader:
            if hasReadHeader:
                ticketMap = {
                    'id': row[0],
                    'type': row[1],
                    'component': row[4],
                    'milestone': row[10],
                    'status': row[11],
                    'resolution': row[12],
                    'summary': row[13],
                    'description': row[14],
                }
                yield ticketMap
            else:
                hasReadHeader = True


def migrateTickets():
    user, password = _githubLogin()
    _log.info('connect to github as user %s', user)
    hub = github.Github(user, password)
    cutplaceRepo = hub.get_user().get_repo('cutplace')
    _log.info('connect to repo %s', cutplaceRepo.name)
    ticketIndex = 0
    startCreateIndex = 7
    endCreateIndex = 99
    existingMilestones = {}
    for milestone in cutplaceRepo.get_milestones():
        existingMilestones[milestone.title] = milestone
    _log.info("existing milestones: %s", existingMilestones)
    for ticketMap in _tracTicketMaps():
        if (ticketIndex >= startCreateIndex) and (ticketIndex <= endCreateIndex):
            title = ticketMap['summary']
            body = ticketMap['description']
            assignee = user
            milestoneTitle = ticketMap['milestone']
            if len(milestoneTitle) != 0:
                if milestoneTitle not in existingMilestones:
                    _log.info(u'create milestone: %s', milestone)
                    newMilestone = cutplaceRepo.create_milestone(milestoneTitle)
                    existingMilestones[milestoneTitle] = newMilestone
                milestone = existingMilestones[milestoneTitle]
                milestoneNumber = milestone.number
            else:
                milestone = None
                milestoneNumber = 0
            _log.info(u"create issue #%d: %s", ticketIndex + 1, title)
            _log.info(u'  %s; %s (%d)', assignee, milestoneTitle, milestoneNumber)
            _log.info(u'  %r', body)
            if milestone is None:
                cutplaceRepo.create_issue(title, body, assignee)
            else:
                cutplaceRepo.create_issue(title, body, assignee, milestone.number)
        ticketIndex += 1

        
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    migrateTickets()

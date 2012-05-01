"""
Tratihubis converts Trac tickets to Github issues by using the following steps:

1. The user manually exports the Trac tickets to convert to a CSV file.
2. Tratihubis reads the CSV file and uses the data to create Github issues and milestones.


Installation
============

To install tratihubis, use ``pip`` or ``easy_install``::

  $ pip install tratihubis

If needed, this also installs the `PyGithub <http://pypi.python.org/pypi/PyGithub/>`_ package.


Usage
=====

Information about Trac tickets to convert has to be provided in a CSV file. To obtain this CSV file, create a
new Trac query using the SQL statement stored in
`query_tickets.sql <https://github.com/roskakori/tratihubis/blob/master/query_tickets.sql>`_ and saving the
result by clicking "Download in other formats: Comma-delimited Text" and choosing for example
``/Users/me/mytool/tickets.csv`` as output file.

Next create a config file to describe how to login to Github and what to convert. For example, you could
store the following in ``/Users/me/mytool/tratihubis.cfg``::

  [tratihubis]
  user = someone
  password = secret
  repo = mytool
  tickets = /Users/me/mytool/tickets.csv

Then run::

  $ tratihubis /Users/me/mytool/tratihubis.cfg


License
=======

Copyright (c) 2012, Thomas Aglassinger. All rights reserved. Distributed under the
`BSD License <http://www.opensource.org/licenses/bsd-license.php>`_.
"""
# Copyright (c) 2012, Thomas Aglassinger
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# * Neither the name of Thomas Aglassinger nor the names of its contributors
#   may be used to endorse or promote products derived from this software
#   without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
import codecs
import collections
import ConfigParser
import csv
import github
import logging
import optparse
import sys

_log = logging.getLogger('tratihubis')

__version__ = "0.1"

_FakeMilestone = collections.namedtuple('FakeMilestone', ['number', 'title'])


class _UTF8Recoder:
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


class _UnicodeCsvReader:
    """
    A CSV reader which will iterate over lines in the CSV file "f",
    which is encoded in the given encoding.
    """
    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        f = _UTF8Recoder(f, encoding)
        self.reader = csv.reader(f, dialect=dialect, **kwds)

    def next(self):  # @ReservedAssignment
        row = self.reader.next()
        return [unicode(s, "utf-8") for s in row]

    def __iter__(self):
        return self


def _tracTicketMaps(ticketsCsvPath):
    """
    Sequence of maps where each items describes the relevant fields of each row from the tickets CSV exported
    from Trac.
    """
    EXPECTED_COLUMN_COUNT = 9
    _log.info(u'read ticket details from "%s"', ticketsCsvPath)
    with open(ticketsCsvPath, "rb") as  ticketCsvFile:
        csvReader = _UnicodeCsvReader(ticketCsvFile)
        hasReadHeader = False
        for row in csvReader:
            columnCount = len(row)
            if columnCount != EXPECTED_COLUMN_COUNT:
                # TODO: Add row number to error message.
                raise ValueError(u'CSV row must have %d columns but has %d: %r' %
                        (EXPECTED_COLUMN_COUNT, columnCount, row))
            if hasReadHeader:
                ticketMap = {
                    'id': long(row[0]),
                    'type': row[1],
                    'owner': row[2],
                    'reporter': row[3],
                    'milestone': row[4],
                    'status': row[5],
                    'resolution': row[6],
                    'summary': row[7],
                    'description': row[8],
                }
                yield ticketMap
            else:
                hasReadHeader = True


def _createMilestoneMap(repo):
    result = {}
    _log.info(u'analyze existing milestones')
    for milestone in repo.get_milestones():
        result[milestone.title] = milestone
        _log.info(u'  %d: %s', milestone.number, milestone.title)
    return result


def migrateTickets(repo, ticketsCsvPath, firstTicketIdToConvert=1, lastTicketIdToConvert=0, pretend=True):
    issueId = 1
    existingMilestones = _createMilestoneMap(repo)
    for ticketMap in _tracTicketMaps(ticketsCsvPath):
        ticketId = ticketMap['id']
        title = ticketMap['summary']
        if (ticketId >= firstTicketIdToConvert) \
                and ((ticketId <= lastTicketIdToConvert) or (lastTicketIdToConvert == 0)):
            body = ticketMap['description']
            assignee = ticketMap['owner'].strip()
            milestoneTitle = ticketMap['milestone'].strip()
            if len(milestoneTitle) != 0:
                if milestoneTitle not in existingMilestones:
                    _log.info(u'add milestone: %s', milestoneTitle)
                    if not pretend:
                        newMilestone = repo.create_milestone(milestoneTitle)
                    else:
                        newMilestone = _FakeMilestone(len(existingMilestones) + 1, milestoneTitle)
                    existingMilestones[milestoneTitle] = newMilestone
                milestone = existingMilestones[milestoneTitle]
                milestoneNumber = milestone.number
            else:
                milestone = None
                milestoneNumber = 0
            _log.info(u"convert ticket #%d to issue #%d: %s", ticketId, issueId, title)
            _log.info(u'  owner=%s; milestone=%s (%d)', assignee, milestoneTitle, milestoneNumber)
            if not pretend:
                if milestone is None:
                    repo.create_issue(title, body, assignee)
                else:
                    repo.create_issue(title, body, assignee, milestone.number)
            issueId += 1
        else:
            _log.info(u'skip ticket #%d: %s', ticketId, title)


def _parsedOptions(arguments):
    assert arguments is not None

    # Parse command line options.
    Usage = """usage: %prog [options] CONFIGFILE

    Convert Trac tickets to Github issues."""
    parser = optparse.OptionParser(
        usage=Usage,
        version="%prog " + __version__
    )
    parser.add_option("-R", "--really", action="store_true", dest="really",
                      help="really perform the conversion")
    parser.add_option("-v", "--verbose", action="store_true", dest="verbose",
                      help="log all actions performed in console")
    (options, others) = parser.parse_args(arguments)
    if len(others) == 0:
        parser.error("CONFIGFILE must be specified")
    elif len(others) > 1:
        parser.error("unknown options must be removed: %s" % others[2:])
    if options.verbose:
        _log.setLevel(logging.DEBUG)

    configPath = others[0]

    return options, configPath


def main(argv=None):
    if argv is None:
        argv = sys.argv

    exitCode = 1
    try:
        options, configPath = _parsedOptions(argv[1:])
        config = ConfigParser.SafeConfigParser()
        config.read(configPath)
        password = config.get('tratihubis', 'password')
        repoName = config.get('tratihubis', 'repo')
        ticketsCsvPath = config.get('tratihubis', 'tickets')
        user = config.get('tratihubis', 'user')
        if not options.really:
            _log.warning(u'no actions are performed unless command line option --really is specified')
        _log.info('log on to github as user "%s"', user)
        hub = github.Github(user, password)
        _log.info('connect to github repo "%s"', repoName)
        repo = hub.get_user().get_repo(repoName)
        migrateTickets(repo, ticketsCsvPath, pretend=not options.really)
        exitCode = 0
    except (EnvironmentError, OSError), error:
        _log.error(error)
    except KeyboardInterrupt:
        _log.warning(u"interrupted by user")
    except Exception, error:
        _log.exception(error)
    return exitCode

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())

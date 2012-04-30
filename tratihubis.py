"""
Tratihubis converts Trac tickets to Github issues.


Installation
============

To install tratihubis, use ``pip`` or ``easy_install``. It requires the PyGithub package available from PyPI::

  $ pip PyGithub
  $ pip tratihubis


Usage
=====

Information about Trac tickets to convert has to be provided in a CSV file. To obtain this CSV file, create a
new Trac query using the SQL statement stored in "query_tickets.sql" and saving the result by clicking
 "Download in other formats: Comma-delimited Text" and choosing for example ``/Users/me/mytool/tickets.csv``
 as output file.
 
Next create a config file to describe how to login to Github and what to convert. For example, you could
store the following in ``/Users/me/mytool/tratihubis.cfg``::
 
  [tratihubis]
  user = someone
  password = secret
  repo = mytool
  tickets = /Users/me/mytool/tickets.csv

Then run::

  tratihubis /Users/me/mytool/tratihubis.cfg


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
import csv
import github
import logging
import os

_log = logging.getLogger('tratihubis')

__version__ = "0.1"


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
    Sequence of maps where each items describes the relevant fields of each row from the tickets CSV exported
    from Trac.
    """
    with open(os.path.expandvars("${HOME}/Desktop/cutplace_trac_tickets.csv"), "rb") as  ticketCsvFile:
        csvReader = UnicodeCsvReader(ticketCsvFile)
        hasReadHeader = False
        for row in csvReader:
            if hasReadHeader:
                ticketMap = {
                    'id': row[0],
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
            assignee = ticketMap['owner']
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

'''
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
new Trac queries using the SQL statement stored in
`query_tickets.sql <https://github.com/roskakori/tratihubis/blob/master/query_tickets.sql>`_  and
`query_comments.sql <https://github.com/roskakori/tratihubis/blob/master/query_comments.sql>`_.   Then
execute the queries and save the results by clicking "Download in other formats: Comma-delimited Text" and
choosing for example ``/Users/me/mytool/tickets.csv`` and ``/Users/me/mytool/comments.csv`` as output files.

Next create a config file to describe how to login to Github and what to convert. For example, you could
store the following in ``~/mytool/tratihubis.cfg``::

  [tratihubis]
  user = someone
  password = secret
  repo = mytool
  tickets = /Users/me/mytool/tickets.csv
  comments = /Users/me/mytool/comments.csv

Then run::

  $ tratihubis ~/mytool/tratihubis.cfg

This tests that the input data and Github information is valid and writes a log to the console describing
which operations would be performed.

To actually create the Github issues, you need to enable to command line option ``--really``::

  $ tratihubis --really ~/mytool/tratihubis.cfg

Be aware that Github issues and milestones cannot be deleted in case you mess up. Your only remedy is to
remove the whole repository and start anew. So make sure that tratihubis does what you want before you
enable ``--really``.

Mapping users
-------------

In case the Trac users have different user names on Github, you can specify a mapping. For example::

   users = johndoe: jdoe78, *: me

This would map the Trac user ``johndoe`` to the Github user ``jdoe78`` and everyone else to the user ``me``.
The default value is::

  users = *:*

This maps every Trac user to a Github user with the same name.

Mapping labels
--------------

Github labels somewhat mimic the functionality Trac stores in the ``type`` and ``resolution`` field of
tickets. By default, Github supports the following labels:

* bug
* duplicate
* enhancement
* invalid
* question
* wontfix

Trac on the other hand has a ``type`` field which by default can be:

* bug
* enhancement
* task

Furthermore closed Trac tickets have a ``resolution`` which, among others, can be:

* duplicate
* invalid
* wontfix

The ``labels`` config option allows to map Trac fields to Github labels. For example::

  labels = type=defect: bug, type=enhancement: enhancement, resolution=wontfix: wontfix

Here, ``labels`` is a comma separated list of mappings taking the form
``<trac-field>=<trac-value>:<github-label>``.

In case types or labels contain other characters than ASCII letters, digits and underscore (_), put them
between quotes:

  labels = type="software defect": bug


Limitations
===========

Milestone without any tickets are skipped.

Milestones lack a due date.

Github issues and comments have the user specified in the config as author, even if a different user opened
the original Trac ticket or wrote the original Trac comment.

Issues and comments have the current time as time stamp instead if time from Trac.

Trac Wiki markup remains instead of being converted to Github markdown.


Support
=======

In case of questions and problems, open an issue at <https://github.com/roskakori/tratihubis/issues>.

To obtain the source code or create your own fork to implement fixes or improvements, visit
<https://github.com/roskakori/tratihubis>.


License
=======

Copyright (c) 2012, Thomas Aglassinger. All rights reserved. Distributed under the
`BSD License <http://www.opensource.org/licenses/bsd-license.php>`_.


Changes
=======

Version 0.3, 2012-05-04

* Added config option ``labels`` to map Trac status and resolution to  Github labels.

Version 0.3, 2012-05-03

* Added config option ``comments`` to convert Trac ticket comments.
* Added closing of issue for which the corresponding Trac ticket has been closed already.
* Added validation of users issues are assigned to. They must have an active Github user.

Version 0.2, 2012-05-02

* Added config option ``users`` to map Trac users to Github users.
* Added binary in order to run ``tratihubis`` instead of ``python -m tratihubis``.
* Changed supposed issue number in log to take existing issues in account.

Version 0.1, 2012-05-01

* Initial release.
'''
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
import os.path
import StringIO
import sys
import token
import tokenize

_log = logging.getLogger('tratihubis')

__version__ = "0.4"

_SECTION = 'tratihubis'
_OPTION_LABELS = 'labels'
_OPTION_USERS = 'users'

_validatedGithubUsers = set()

_FakeMilestone = collections.namedtuple('_FakeMilestone', ['number', 'title'])
_FakeIssue = collections.namedtuple('_FakeIssue', ['number', 'title', 'body', 'state'])


class _ConfigError(Exception):
    def __init__(self, option, message):
        assert option is not None
        assert message is not None
        Exception.__init__(self, u'cannot process config option "%s" in section [%s]: %s' % (option, _SECTION, message))


class _CsvDataError(Exception):
    def __init__(self, csvPath, rowIndex, message):
        assert csvPath is not None
        assert rowIndex is not None
        assert rowIndex >= 0
        assert message is not None
        Exception.__init__(self, u'%s:%d: %s' % (os.path.basename(csvPath), rowIndex + 1, message))


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


class _LabelTransformations(object):
    def __init__(self, repo, definition):
        assert repo is not None

        self._transformations = []
        self._labelMap = {}
        if definition:
            self._buildLabelMap(repo)
            self._buildTransformations(repo, definition)

    def _buildLabelMap(self, repo):
        assert repo is not None

        _log.info(u'analyze existing labels')
        self._labelMap = {}
        for label in repo.get_labels():
            _log.debug(u'  found label "%s"', label.name)
            self._labelMap[label.name] = label
        _log.info(u'  found %d labels', len(self._labelMap))

    def _buildTransformations(self, repo, definition):
        assert repo is not None
        assert definition is not None

        STATE_AT_TRAC_FIELD = 'f'
        STATE_AT_COMPARISON_OPERATOR = '='
        STATE_AT_TRAC_VALUE = 'v'
        STATE_AT_COLON = ':'
        STATE_AT_LABEL = 'l'
        STATE_AT_COMMA = ','

        self._transformations = []
        state = STATE_AT_TRAC_FIELD
        for tokenType, tokenText, _, _, _ in tokenize.generate_tokens(StringIO.StringIO(definition).readline):
            if tokenType == token.STRING:
                tokenText = tokenText[1:len(tokenText) - 1]
            if state == STATE_AT_TRAC_FIELD:
                tracField = tokenText
                tracValue = None
                labelValue = None
                state = STATE_AT_COMPARISON_OPERATOR
            elif state == STATE_AT_COMPARISON_OPERATOR:
                if tokenText != '=':
                    raise _ConfigError(_OPTION_LABELS, \
                            u'Trac field "%s" must be followed by \'=\' instead of %r' \
                            % (tracField, tokenText))
                state = STATE_AT_TRAC_VALUE
            elif state == STATE_AT_TRAC_VALUE:
                tracValue = tokenText
                state = STATE_AT_COLON
            elif state == STATE_AT_COLON:
                if tokenText != ':':
                    raise _ConfigError(_OPTION_LABELS, \
                            u'value for comparison "%s" with Trac field "%s" must be followed by \':\' instead of %r' \
                            % (tracValue, tracField, tokenText))
                state = STATE_AT_LABEL
            elif state == STATE_AT_LABEL:
                labelValue = tokenText
                if not labelValue in self._labelMap:
                    raise _ConfigError(_OPTION_LABELS, \
                            u'unknown label "%s" must be replaced by one of: %s' \
                            % (labelValue, sorted(self._labelMap.keys())))
                self._transformations.append((tracField, tracValue, labelValue))
                state = STATE_AT_COMMA
            elif state == STATE_AT_COMMA:
                if (tokenType != token.ENDMARKER) and (tokenText != ','):
                    raise _ConfigError(_OPTION_LABELS, \
                            u'label transformation for Trac field "%s" must end with \',\' instead of %r' \
                            % (tracField, tokenText))
                state = STATE_AT_TRAC_FIELD
            else:
                assert False, u'state=%r' % state

    def labelFor(self, tracField, tracValue):
        assert tracField
        assert tracValue is not None
        result = None
        transformationIndex = 0
        while (result is None) and (transformationIndex < len(self._transformations)):
            transformedField, transformedValueToCompareWith, transformedLabel = \
                    self._transformations[transformationIndex]
            if (transformedField == tracField) and (transformedValueToCompareWith == tracValue):
                assert transformedLabel in self._labelMap
                result = self._labelMap[transformedLabel]
            else:
                transformationIndex += 1
        return result


def _getConfigOption(config, name, required=True, defaultValue=None):
    try:
        result = config.get(_SECTION, name)
    except ConfigParser.NoOptionError:
        if required:
            raise _ConfigError(name, 'config must contain a value for this option')
        result = defaultValue
    except ConfigParser.NoSectionError:
        raise _ConfigError(name, u'config must contain this section')
    return result


def _shortened(text):
    assert text is not None
    THRESHOLD = 30
    if len(text) > THRESHOLD:
        result = text[:THRESHOLD] + '...'
    else:
        result = text
    return result


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
        for rowIndex, row in enumerate(csvReader):
            columnCount = len(row)
            if columnCount != EXPECTED_COLUMN_COUNT:
                raise _CsvDataError(ticketsCsvPath, rowIndex,
                        u'ticket row must have %d columns but has %d: %r' %
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
    def addMilestones(targetMap, state):
        for milestone in repo.get_milestones(state=state):
            _log.debug(u'  %d: %s', milestone.number, milestone.title)
            targetMap[milestone.title] = milestone
    result = {}
    _log.info(u'analyze existing milestones')
    addMilestones(result, 'open')
    addMilestones(result, 'closed')
    _log.info(u'  found %d milestones', len(result))
    return result


def _createIssueMap(repo):
    def addIssues(targetMap, state):
        for issue in repo.get_issues(state=state):
            _log.debug(u'  %s: (%s) %s', issue.number, issue.state, issue.title)
            targetMap[issue.number] = issue
    result = {}
    _log.info(u'analyze existing issues')
    addIssues(result, 'open')
    addIssues(result, 'closed')
    _log.info(u'  found %d issues', len(result))
    return result


def _createTicketToCommentsMap(commentsCsvPath):
    EXPECTED_COLUMN_COUNT = 4
    result = {}
    if commentsCsvPath is not None:
        _log.info(u'read ticket comments from "%s"', commentsCsvPath)
        with open(commentsCsvPath, "rb") as  commentsCsvFile:
            csvReader = _UnicodeCsvReader(commentsCsvFile)
            hasReadHeader = False
            for rowIndex, row in enumerate(csvReader):
                columnCount = len(row)
                if columnCount != EXPECTED_COLUMN_COUNT:
                    raise _CsvDataError(commentsCsvPath, rowIndex,
                            u'comment row must have %d columns but has %d: %r' %
                            (EXPECTED_COLUMN_COUNT, columnCount, row))
                if hasReadHeader:
                    commentMap = {
                        'id': long(row[0]),
                        'author': row[2],
                        'body': row[3],
                    }
                    ticketId = commentMap['id']
                    ticketComments = result.get(ticketId)
                    if ticketComments is None:
                        ticketComments = []
                        result[ticketId] = ticketComments
                    ticketComments.append(commentMap)
                else:
                    hasReadHeader = True
    return result


def migrateTickets(hub, repo, ticketsCsvPath, commentsCsvPath=None, firstTicketIdToConvert=1, lastTicketIdToConvert=0, labelMapping=None, userMapping="*:*", pretend=True):
    assert hub is not None
    assert repo is not None
    assert ticketsCsvPath is not None
    assert userMapping is not None

    tracTicketToCommentsMap = _createTicketToCommentsMap(commentsCsvPath)
    existingIssues = _createIssueMap(repo)
    existingMilestones = _createMilestoneMap(repo)
    tracToGithubUserMap = _createTracToGithubUserMap(hub, userMapping)
    labelTransformations = _LabelTransformations(repo, labelMapping)

    def possiblyAddLabel(labels, tracField, tracValue):
        label = labelTransformations.labelFor(tracField, tracValue)
        if label is not None:
            _log.info('  add label %s', label.name)
            if not pretend:
                labels.append(label.name)

    fakeIssueId = 1 + len(existingIssues)
    for ticketMap in _tracTicketMaps(ticketsCsvPath):
        ticketId = ticketMap['id']
        title = ticketMap['summary']
        if (ticketId >= firstTicketIdToConvert) \
                and ((ticketId <= lastTicketIdToConvert) or (lastTicketIdToConvert == 0)):
            body = ticketMap['description']
            tracOwner = ticketMap['owner'].strip()
            githubAssignee = _githubUserFor(hub, tracToGithubUserMap, tracOwner)
            milestoneTitle = ticketMap['milestone'].strip()
            if len(milestoneTitle) != 0:
                if milestoneTitle not in existingMilestones:
                    _log.info(u'add milestone: %s', milestoneTitle)
                    print existingMilestones
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
            _log.info(u'convert ticket #%d: %s', ticketId, _shortened(title))
            if not pretend:
                if milestone is None:
                    issue = repo.create_issue(title, body, githubAssignee)
                else:
                    issue = repo.create_issue(title, body, githubAssignee, milestone.number)
            else:
                issue = _FakeIssue(fakeIssueId, title, body, 'open')
                fakeIssueId += 1
            _log.info(u'  issue #%s: owner=%s-->%s; milestone=%s (%d)',
                    issue.number, tracOwner, githubAssignee, milestoneTitle, milestoneNumber)
            labels = []
            possiblyAddLabel(labels, 'type', ticketMap['type'])
            possiblyAddLabel(labels, 'resolution', ticketMap['resolution'])
            if len(labels) > 0:
                issue.edit(labels=labels)
            commentsToAdd = tracTicketToCommentsMap.get(ticketId)
            if commentsToAdd is not None:
                for comment in commentsToAdd:
                    commentBody = comment['body']
                    commentAuthor = _githubUserFor(repo, tracToGithubUserMap, comment['author'], False)
                    _log.info(u'  add comment by %s: %r', commentAuthor, _shortened(commentBody))
                    if not pretend:
                        assert issue is not None
                        issue.create_comment(commentBody)
            if ticketMap['status'] == 'closed':
                _log.info(u'  close issue')
                if not pretend:
                    issue.edit(state='closed')
        else:
            _log.info(u'skip ticket #%d: %s', ticketId, title)


def _parsedOptions(arguments):
    assert arguments is not None

    # Parse command line options.
    Usage = 'usage: %prog [options] CONFIGFILE\n\n  Convert Trac tickets to Github issues.'
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
        parser.error(u"CONFIGFILE must be specified")
    elif len(others) > 1:
        parser.error(u"unknown options must be removed: %s" % others[1:])
    if options.verbose:
        _log.setLevel(logging.DEBUG)

    configPath = others[0]

    return options, configPath


def _validateGithubUser(hub, tracUser, githubUser):
    assert hub is not None
    assert tracUser is not None
    assert githubUser is not None
    if githubUser not in _validatedGithubUsers:
        try:
            _log.debug(u'  check for Github user "%s"', githubUser)
            hub.get_user(githubUser)
        except:
            # FIXME: After PyGithub API raises a predictable error, use  "except WahteverException".
            raise _ConfigError(_OPTION_USERS,
                    u'Trac user "%s" must be mapped to an existing Github user instead of "%s"' \
                    % (tracUser, githubUser))
        _validatedGithubUsers.add(githubUser)


def _createTracToGithubUserMap(hub, definition):
    result = {}
    for mapping in definition.split(','):
        words = [word.strip() for word in mapping.split(':')]
        if words:
            if len(words) != 2:
                raise _ConfigError(_OPTION_USERS, u'mapping must use syntax "trac-user: github-user" but is: "%s"' % mapping)
            tracUser, githubUser = words
            if len(tracUser) == 0:
                raise _ConfigError(_OPTION_USERS, u'Trac user must not be empty: "%s"' % mapping)
            if len(githubUser) == 0:
                raise _ConfigError(_OPTION_USERS, u'Github user must not be empty: "%s"' % mapping)
            existingMappedGithubUser = result.get(tracUser)
            if existingMappedGithubUser is not None:
                raise _ConfigError(_OPTION_USERS,
                        u'Trac user "%s" must be mapped to only one Github user instead of "%s" and "%s"' \
                         % (tracUser, existingMappedGithubUser, githubUser))
            result[tracUser] = githubUser
            if githubUser != '*':
                _validateGithubUser(hub, tracUser, githubUser)
    return result


def _githubUserFor(hub, tracToGithubUserMap, tracUser, validate=True):
    assert tracToGithubUserMap is not None
    assert tracUser is not None
    result = tracToGithubUserMap.get(tracUser)
    if result is None:
        result = tracToGithubUserMap.get('*')
        if result is None:
            raise _ConfigError(_OPTION_USERS, u'Trac user "%s" must be mapped to a Github user')
    if result == '*':
        result = tracUser
    if validate:
        _validateGithubUser(hub, tracUser, result)
    return result


def main(argv=None):
    if argv is None:
        argv = sys.argv

    exitCode = 1
    try:
        options, configPath = _parsedOptions(argv[1:])
        config = ConfigParser.SafeConfigParser()
        config.read(configPath)
        commentsCsvPath = _getConfigOption(config, 'comments', False)
        labelMapping = _getConfigOption(config, 'labels', False)
        password = _getConfigOption(config, 'password')
        repoName = _getConfigOption(config, 'repo')
        ticketsCsvPath = _getConfigOption(config, 'tickets', False, 'tickets.csv')
        user = _getConfigOption(config, 'user')
        userMapping = _getConfigOption(config, 'users', False, '*:*')
        if not options.really:
            _log.warning(u'no actions are performed unless command line option --really is specified')
        _log.info(u'log on to github as user "%s"', user)
        hub = github.Github(user, password)
        _log.info(u'connect to github repo "%s"', repoName)
        repo = hub.get_user().get_repo(repoName)
        migrateTickets(hub, repo, ticketsCsvPath, commentsCsvPath, userMapping=userMapping,
                labelMapping=labelMapping, pretend=not options.really)
        exitCode = 0
    except (EnvironmentError, OSError, _ConfigError, _CsvDataError), error:
        _log.error(error)
    except KeyboardInterrupt:
        _log.warning(u"interrupted by user")
    except Exception, error:
        _log.exception(error)
    return exitCode


def _mainEntryPoint():
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())


if __name__ == "__main__":
    _mainEntryPoint()

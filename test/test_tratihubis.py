'''
Tests for tratihubis.
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
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS 'AS IS'
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
import ConfigParser
import github
import logging
import os.path
import unittest

import tratihubis

_TEST_CONFIG_PATHS = [
    os.path.expanduser(os.path.join('~', '.tratihubis_test')),
    os.path.expanduser(os.path.join('~', 'tratihubis_test.cfg'))
]


class _HubbedTest(unittest.TestCase):
    '''
    Like `unittest.TestCase` but with a `setUp()` that connects to Github and offers a ``hub`` property.
    '''
    def setUp(self):
        config = ConfigParser.SafeConfigParser()
        config.read(_TEST_CONFIG_PATHS)
        if not config.has_section('tratihubis'):
            raise ConfigParser.Error(u'test user and password must be specified in section [tratihubis] ' \
                    + 'in one of the following files: %s' % _TEST_CONFIG_PATHS)
        password = config.get('tratihubis', 'password')
        user = config.get('tratihubis', 'user')
        self.hub = github.Github(user, password)


class UserMapTest(_HubbedTest):
    def testCanCreateValidUserMap(self):
        userMap = tratihubis._createTracToGithubUserMap(self.hub, 'hugo: sepp, *: roskakori')
        self.assertEqual(userMap, {'*': 'roskakori', 'hugo': 'sepp'})
        userMap = tratihubis._createTracToGithubUserMap(self.hub, '*:*')
        self.assertEqual(userMap, {'*': '*'})
        userMap = tratihubis._createTracToGithubUserMap(self.hub, ' * : * ')
        self.assertEqual(userMap, {'*': '*'})

    def testFailsOnDuplicateUser(self):
        self.assertRaises(tratihubis._ConfigError, tratihubis._createTracToGithubUserMap, \
                self.hub, 'hugo: sepp, hugo: resi')


class TratihubisTest(_HubbedTest):
    def _testCanConvertTicketsCsv(self, ticketsCsvPath, commentsCsvPath=None):
        repoName = 'tratihubis'
        userMapping = 'johndoe: roskakori, *: roskakori'
        repo = self.hub.get_user().get_repo(repoName)
        tratihubis.migrateTickets(self.hub, repo, ticketsCsvPath, commentsCsvPath, userMapping=userMapping, pretend=True)

    def testCanConvertTestTicketsCsv(self):
        self._testCanConvertTicketsCsv(os.path.join('test', 'test_tickets.csv'), os.path.join('test', 'test_comments.csv'))

    def testCanConvertCutplaceTicketsCsv(self):
        self._testCanConvertTicketsCsv(os.path.join('test', 'cutplace_tickets.csv'))


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    logging.basicConfig(level=logging.INFO)
    unittest.main()

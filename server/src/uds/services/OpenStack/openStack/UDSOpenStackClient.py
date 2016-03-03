# -*- coding: utf-8 -*-

#
# Copyright (c) 2012 Virtual Cable S.L.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright notice,
#      this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright notice,
#      this list of conditions and the following disclaimer in the documentation
#      and/or other materials provided with the distribution.
#    * Neither the name of Virtual Cable S.L. nor the names of its contributors
#      may be used to endorse or promote products derived from this software
#      without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

'''
.. moduleauthor:: Adolfo Gómez, dkmaster at dkmon dot com
'''
# pylint: disable=maybe-no-member
from uds.core.util.Cache import Cache

import logging
import requests
import json
import six
import hashlib
import dateutil.parser


# Python bindings for OpenNebula
from .common import sanitizeName

__updated__ = '2016-03-03'

logger = logging.getLogger(__name__)

# Required: Authentication v3


# This is a vary basic implementation for what we need from openstack
# This does not includes (nor it is intention) full API implementation, just the parts we need
# Theese are related to auth, compute & network basically

# In case we Cache time for endpoints. This is more likely to not change never, so we will tray to keep it as long as we can (1 hour for example?)
# ENDPOINTS_TIMEOUT = 1 * 3600

# Helpers
def ensureResponseIsValid(response, errMsg=None):
    if response.ok is False:
        if errMsg is None:
            errMsg = 'Error checking response'
        logger.error('{}: {}'.format(errMsg, response.content))
        print response.content
        print response
        raise Exception(errMsg)


# Decorators
def authRequired(func):
    def ensurer(obj, *args, **kwargs):
        obj.ensureAuthenticated()
        return func(obj, *args, **kwargs)
    return ensurer

def authProjectRequired(func):
    def ensurer(obj, *args, **kwargs):
        if obj._projectId is None:
            raise Exception('Need a project for method {}'.format(func))
        obj.ensureAuthenticated()
        return func(obj, *args, **kwargs)
    return ensurer


class UDSOpenStackClient(object):
    cache = Cache('uds-openstack')

    PUBLIC = 'public'
    PRIVATE = 'private'
    INTERNAL = 'url'

    def __init__(self, host, port, domain, username, password, useSSL=False, projectId=None, region=None, access=None):
        self._authenticated = False
        self._tokenId = None
        self._catalog = None

        self._access = UDSOpenStackClient.PUBLIC if access is None else access
        self._host, self._port = host, int(port)
        self._domain, self._username, self._password = domain, username, password
        self._userId = None
        self._projectId = projectId
        self._project = None
        self._region = region
        self._timeout = 10

        self._authUrl = 'http{}://{}:{}/'.format('s' if useSSL else '', host, port)

        # Generates a hash for auth + credentials
        # h = hashlib.md5()
        # h.update(six.binary_type(username))
        # h.update(six.binary_type(password))
        # h.update(six.binary_type(host))
        # h.update(six.binary_type(port))
        # h.update(six.binary_type(tenant))

        # self._cacheKey = h.hexdigest()

    def _getEndpointFor(self, type_):  # If no region is indicatad, first endpoint is returned
        for i in self._catalog:
            if i['type'] == type_:
                for j in i['endpoints']:
                    if j['interface'] == self._access and (self._region is None or j['region'] == self._region):
                        return j['url']

    def _requestHeaders(self):
        headers = {'content-type': 'application/json'}
        if self._tokenId is not None:
            headers['X-Auth-Token'] = self._tokenId

        return headers

    def authPassword(self):
        data = {
            'auth': {
                'identity': {
                    'methods': [
                        'password'
                    ],
                    'password': {
                        'user': {
                            'name': self._username,
                            'domain': {
                                'name': 'Default' if self._domain is None else self._domain
                            },
                            'password': self._password
                        }
                    }
                }
            }
        }

        if self._projectId is None:
            data['auth']['scope'] = 'unscoped'
        else:
            data['auth']['scope'] = {
                'project': {
                    'id': self._projectId
                }
            }

        r = requests.post(self._authUrl + 'v3/auth/tokens',
                          data=json.dumps(data),
                          headers={'content-type': 'application/json'},
                          verify=False,
                          timeout=self._timeout)

        ensureResponseIsValid(r, 'Invalid Credentials')

        self._authenticated = True
        self._tokenId = r.headers['X-Subject-Token']
        # Extract the token id
        token = r.json()['token']
        self._userId = token['user']['id']
        validity = (dateutil.parser.parse(token['expires_at']).replace(tzinfo=None) - dateutil.parser.parse(token['issued_at']).replace(tzinfo=None)).seconds - 60


        logger.debug('The token {} will be valid for {}'.format(self._tokenId, validity))

        # Now, if endpoints are present (only if tenant was specified), store & cache them
        if self._projectId is not None:
            self._catalog = token['catalog']


    def ensureAuthenticated(self):
        if self._authenticated is False:
            self.authPassword()


    @authRequired
    def listProjects(self):
        r = requests.get(self._authUrl + 'v3/users/{user_id}/projects'.format(user_id=self._userId),
                         headers=self._requestHeaders())

        ensureResponseIsValid(r, 'List Tenants')

        for p in json.loads(r.content)['projects']:
            yield p


    @authRequired
    def listRegions(self):
        r = requests.get(self._authUrl + 'v3/regions/',
                         headers=self._requestHeaders())

        ensureResponseIsValid(r, 'List Regions')

        for r in json.loads(r.content)['regions']:
            yield r


    @authProjectRequired
    def listVms(self):
        url = self._getEndpointFor('compute') + '/servers'
        while True:
            r = requests.get(url, headers=self._requestHeaders())

            ensureResponseIsValid(r, 'List Vms')

            json = r.json()

            for v in json['servers']:
                yield { 'name': v['name'], 'id': v['id'] }

            if 'next' not in json:
                break

            url = json['next']

    @authProjectRequired
    def listImages(self):
        url = self._getEndpointFor('image') + '/v2/images?status=active'
        while True:
            r = requests.get(url, headers=self._requestHeaders())

            ensureResponseIsValid(r, 'List Images')

            json = r.json()

            for i in json['images']:
                yield { 'name': i['name'], 'size': i['size'], 'visibility': i['visibility'], 'format': i['disk_format'] }

            if 'next' not in json:
                break

            url = json['next']

    @authProjectRequired
    def listVolumes(self):
        url = self._getEndpointFor('volumev2') + '/volumes'

        while True:
            r = requests.get(url, headers=self._requestHeaders())

            ensureResponseIsValid(r, 'List Volumes')

            json = r.json()

            for i in json['volumes']:
                yield { 'id':  i['id'], 'name': i['name'] }

            if 'next' not in json:
                break

            url = json['next']


    def testConection(self):
        # First, ensure requested api is supported
        # We need api version 3.2 or greater

        r = requests.get(self._authUrl,
                         headers=self._requestHeaders())

        for v in r.json()['versions']['values']:
            if v['id'] >= 'v3.2':
                # Tries to authenticate
                try:
                    self.authPassword()
                    return True
                except Exception:
                    return False

        return False
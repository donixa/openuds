# -*- coding: utf-8 -*-

#
# Copyright (c) 2012-2019 Virtual Cable S.L.
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

"""
.. moduleauthor:: Adolfo Gómez, dkmaster at dkmon dot com
"""
import logging
import typing

from django.db import models
from django.db.models import signals

from uds.core.util import log
from .managed_object_model import ManagedObjectModel
from .tag import TaggingMixin

# Not imported at runtime, just for type checking
if typing.TYPE_CHECKING:
    from uds.core import services

logger = logging.getLogger(__name__)


class Provider(ManagedObjectModel, TaggingMixin):  # type: ignore
    """
    A Provider represents the Service provider itself, (i.e. a KVM Server or a Terminal Server)
    """

    # pylint: disable=model-missing-unicode
    maintenance_mode = models.BooleanField(default=False, db_index=True)

    class Meta(ManagedObjectModel.Meta):
        """
        Meta class to declare default order
        """
        ordering = ('name',)
        app_label = 'uds'

    def getType(self) -> typing.Type['services.ServiceProvider']:
        '''
        Get the type of the object this record represents.

        The type is Python type, it obtains this type from ServiceProviderFactory and associated record field.

        Returns:
            The python type for this record object
        '''
        from uds.core import services  # pylint: disable=redefined-outer-name
        type_ = services.factory().lookup(self.data_type)
        if type_:
            return type_
        return services.ServiceProvider  # Basic Service implementation. Will fail if we try to use it, but will be ok to reference it

    def getInstance(self, values: typing.Optional[typing.Dict[str, str]] = None) -> 'services.ServiceProvider':
        prov: services.ServiceProvider = typing.cast('services.ServiceProvider', super().getInstance(values=values))
        # Set uuid
        prov.setUuid(self.uuid)
        return prov

    def isInMaintenance(self) -> bool:
        return self.maintenance_mode

    def __str__(self):
        return '{} of type {} (id:{})'.format(self.name, self.data_type, self.id)

    @staticmethod
    def beforeDelete(sender, **kwargs):
        """
        Used to invoke the Provider class "Destroy" before deleting it from database.

        The main purpuse of this hook is to call the "destroy" method of the object to delete and
        to clear related data of the object (environment data such as own storage, cache, etc...

        :note: If destroy raises an exception, the deletion is not taken.
        """
        from uds.core.util.permissions import clean

        toDelete = kwargs['instance']
        logger.debug('Before delete service provider %s', toDelete)

        # Only tries to get instance if data is not empty
        if toDelete.data != '':
            s = toDelete.getInstance()
            s.destroy()
            s.env.clearRelatedData()

        # Clears related logs
        log.clearLogs(toDelete)

        # Clears related permissions
        clean(toDelete)


# : Connects a pre deletion signal to Provider
signals.pre_delete.connect(Provider.beforeDelete, sender=Provider)

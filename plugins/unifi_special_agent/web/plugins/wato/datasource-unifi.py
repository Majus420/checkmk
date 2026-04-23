#!/usr/bin/env python3
# -*- encoding: utf-8; py-indent-offset: 4 -*-
#
#  _   _       _  __ _ 
# | | | |     (_)/ _(_)
# | | | |_ __  _| |_ _ 
# | | | | '_ \| |  _| |
# | |_| | | | | | | | |
#  \___/|_| |_|_|_| |_|
#
# created: 01/2022
#
# Original author: Frank Baier <dev@baier-nt.de>
# Fork maintained by: Marius Gielnik <marius.gielnik@gmail.com>
#
# Changelog:
#   1.0 - Removed Version: 1.0 output causing false WARN on Check_MK service
#
from cmk.gui.plugins.wato.special_agents.common import RulespecGroupDatasourceProgramsHardware
from cmk.gui.i18n import _
from cmk.gui.plugins.wato.utils import (
    HostRulespec,
    IndividualOrStoredPassword,
    rulespec_registry,
)
from cmk.gui.valuespec import (
    Checkbox,
    Dictionary,
    DropdownChoice,
    Integer,
    ListOfStrings,
    TextAscii,
    Transform,
)


def _special_agents_unifi_transform(v):
    v.setdefault("verify_cert", False)
    v.setdefault("port", 8443)
    v.setdefault("sites", ["all"])
    v.setdefault("use_hostname", False)
    v.setdefault("device_piggyback", False)
    v.setdefault("user_piggyback", False)
    v.setdefault("user_piggyback_name", "ip")
    v.setdefault("udm_pro", False)
    return v


def _valuespec_special_agents_unifi():
    return Transform(
        Dictionary(
            title=_("Unifi Controller"),
            elements=[
                ("user", TextAscii(
                    title=_("Username"),
                    allow_empty=False,
                )),
                ("password", IndividualOrStoredPassword(
                    title=_("Password"),
                    allow_empty=False,
                )),
                ("port",
                 Integer(
                     title=_('TCP port number'),
                     help=_('Port number that the Unifi Controller is listening on. The default is 8443.'
                            'The new Controller generation (G2) uses 443.'),
                     default_value=443,
                     minvalue=1,
                     maxvalue=65535,
                 )),
                ("verify_cert",
                 DropdownChoice(
                     title=_("SSL certificate verification"),
                     default_value=False,
                     choices=[
                         (True, _("Activate")),
                         (False, _("Deactivate")),
                     ],
                 )),
                ("udm_pro",
                 Checkbox(
                     title=_("UDM-Pro API"),
                     label=_("Using UDMP-Pro API-Endpoints."
                             "For CloudKey (UCK) or self depoyed installations do not enable!"),
                     default_value=False,
                     true_label=_("UDM-Pro API"),
                     false_label=_("UCK"),
                 )),
                ("controller", TextAscii(
                    title=_("Controller"),
                    help=_('Unifi controller IP or hostname (extra value in case a docker overlay network is used)'),
                    allow_empty=True,
                )),
                ("use_hostname",
                 Checkbox(
                     title=_("Use hostname"),
                     label=_("Use hostname instead of IP for check execution."
                             "If a special hostname is set this will be overwritten."),
                     default_value=False,
                     true_label=_("use hostname"),
                     false_label=_("use IP"),
                 )),
                ("sites",
                 ListOfStrings(
                     title=_("Sites to query"),
                     help=_("Use this option to set which sites should be checked by the special agent."
                            "If this is disabled only overall information is given."
                            "If you enabled it and set \"all\", all sites are given"
                            "This will send piggyback data in the name of a Unifi site."),
                     default_value='all',
                     size=32,
                     allow_empty=True,
                 )),
                ("device_piggyback",
                 Checkbox(
                     title=_("Create Unifi Devices."),
                     label=_("Create Unifi Devices via piggyback data. Sites must be queried."),
                     default_value=False,
                     true_label=_("create CheckMK hosts for clients"),
                     false_label=_("do not create CheckMK hosts for clients"),
                 )),
                ("user_piggyback",
                 DropdownChoice(
                     title=_("User/Client Device creation"),
                     default_value=False,
                     choices=[
                         (False, _("deactivated")),
                         ("create_user",
                          _('Create CheckMK host per User (multiple detailed services per client/user host)')),
                         ("create_user_site", _('Create Users in Unifi Site Host (One Service per Host))')),
                     ],
                 )),
                ("user_piggyback_name",
                 DropdownChoice(
                     title=_("User/Client Name-Schema"),
                     default_value="ip",
                     choices=[
                         ("mac", _('using MAC-Address')),
                         ("name", _('using Unifi name')),
                         ("hostname", _('using detected hostname')),
                         ("note", _('using Unifi note')),
                         ("ip", _('using IP-Adress (Should be fixed in best case.)')),
                         ("user_id", _('using Unifi internal UserID')),
                     ],
                 )),
            ],
            optional_keys=["sites", 'controller'],
        ),
        forth=_special_agents_unifi_transform,
    )


rulespec_registry.register(
    HostRulespec(
        group=RulespecGroupDatasourceProgramsHardware,
        name="special_agents:unifi",
        title=lambda: _("Unifi Controller"),
        valuespec=_valuespec_special_agents_unifi,
    ))

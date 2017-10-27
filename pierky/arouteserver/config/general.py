# Copyright (C) 2017 Pier Carlo Chiodi
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging

from .base import ConfigParserBase, convert_next_hop_policy, \
                  convert_maxprefix_peeringdb
from .validators import *
from ..errors import ConfigError, ARouteServerError


class ConfigParserGeneral(ConfigParserBase):

    ROOT = "cfg"

    # outbound   communities used by the route server to signal
    #            something to its clients
    # inbound    communities sent by clients to the route server
    #            to ask it to perform some action
    # internal   communities used by the route server internally,
    #            neither received nor propagated to clients
    # peer_as    the last part of the community must be the ASN
    #            with regards of which the requested action must
    #            be performed
    # dyn_val    the last part of the community contains a value
    #            that is locally significant to the function that
    #            the BGP community is responsible for
    COMMUNITIES_SCHEMA = {
        "origin_present_in_as_set": { "type": "outbound" },
        "origin_not_present_in_as_set": { "type": "outbound" },
        "prefix_present_in_as_set": { "type": "outbound" },
        "prefix_not_present_in_as_set": { "type": "outbound" },
        "prefix_validated_via_rpki_roas": { "type": "outbound" },

        "blackholing": { "type": "inbound" },

        "do_not_announce_to_any": { "type": "inbound" },
        "do_not_announce_to_peer": { "type": "inbound", "peer_as": True },
        "announce_to_peer": { "type": "inbound", "peer_as": True },
        "do_not_announce_to_peers_with_rtt_lower_than": { "type": "inbound", "dyn_val": True, "rtt": True },
        "do_not_announce_to_peers_with_rtt_higher_than": { "type": "inbound", "dyn_val": True, "rtt": True },
        "announce_to_peers_with_rtt_lower_than": { "type": "inbound", "dyn_val": True, "rtt": True },
        "announce_to_peers_with_rtt_higher_than": { "type": "inbound", "dyn_val": True, "rtt": True },

        "prepend_once_to_any": { "type": "inbound" },
        "prepend_twice_to_any": { "type": "inbound" },
        "prepend_thrice_to_any": { "type": "inbound" },
        "prepend_once_to_peer": { "type": "inbound", "peer_as": True },
        "prepend_twice_to_peer": { "type": "inbound", "peer_as": True },
        "prepend_thrice_to_peer": { "type": "inbound", "peer_as": True },
        "prepend_once_to_peers_with_rtt_lower_than": { "type": "inbound", "dyn_val": True, "rtt": True },
        "prepend_twice_to_peers_with_rtt_lower_than": { "type": "inbound", "dyn_val": True, "rtt": True },
        "prepend_thrice_to_peers_with_rtt_lower_than": { "type": "inbound", "dyn_val": True, "rtt": True },
        "prepend_once_to_peers_with_rtt_higher_than": { "type": "inbound", "dyn_val": True, "rtt": True },
        "prepend_twice_to_peers_with_rtt_higher_than": { "type": "inbound", "dyn_val": True, "rtt": True },
        "prepend_thrice_to_peers_with_rtt_higher_than": { "type": "inbound", "dyn_val": True, "rtt": True },

        "add_noexport_to_any": { "type": "inbound" },
        "add_noadvertise_to_any": { "type": "inbound" },
        "add_noexport_to_peer": { "type": "inbound", "peer_as": True },
        "add_noadvertise_to_peer": { "type": "inbound", "peer_as": True },

        "reject_cause": { "type": "internal", "dyn_val": True },
        "rejected_route_announced_by": { "type": "internal", "dyn_val": True },
    }

    @staticmethod
    def new_community_validator(rs_as_macro, peer_as=False, dyn_val=False):
        return {
            comm_type: validator_class(
                rs_as_macro, mandatory=False,
                peer_as_macro_needed=peer_as,
                dyn_val_macro_needed=dyn_val
            ) for comm_type, validator_class in [
                ("std", ValidatorCommunityStd),
                ("lrg", ValidatorCommunityLrg),
                ("ext", ValidatorCommunityExt)
            ]
        }

    def parse(self):
        """
        Contents of cfg dict is updated/normalized by validators.
        """

        errors = False

        schema = {
            "cfg": {
                "rs_as": ValidatorASN(),
                "router_id": ValidatorIPv4Addr(mandatory=True),
                "prepend_rs_as": ValidatorBool(default=False),
                "path_hiding": ValidatorBool(default=True),
                "passive": ValidatorBool(default=True),
                "gtsm": ValidatorBool(default=False),
                "add_path": ValidatorBool(default=False),
                "filtering": {
                    "next_hop": {
                        "policy": ValidatorOption("policy",
                                                  ("strict", "same-as",
                                                   "authorized_addresses"),
                                                  default="strict"),
                    },
                    "ipv4_pref_len": ValidatorIPMinMaxLen(4,
                                                          default={"min": 8,
                                                                   "max": 24}),
                    "ipv6_pref_len": ValidatorIPMinMaxLen(6,
                                                          default={"min": 12,
                                                                   "max": 48}),
                    "global_black_list_pref": ValidatorListOf(
                        ValidatorPrefixListEntry, mandatory=False,
                    ),
                    "max_as_path_len": ValidatorMaxASPathLen(default=32),
                    "reject_invalid_as_in_as_path": ValidatorBool(default=True),
                    "transit_free": {
                        "action": ValidatorOption("action",
                                                  ("reject", "warning"),
                                                  mandatory=False,
                                                  default="reject"),
                        "asns": ValidatorASNList(mandatory=False)
                    },
                    "irrdb": {
                        "enforce_origin_in_as_set": ValidatorBool(default=True),
                        "enforce_prefix_in_as_set": ValidatorBool(default=True),
                        "allow_longer_prefixes": ValidatorBool(default=False),
                        "tag_as_set": ValidatorBool(default=True),
                        "peering_db": ValidatorBool(default=False),
                        "use_rpki_roas_as_route_objects": {
                            "enabled": ValidatorBool(default=False),
                            "source": ValidatorOption("source",
                                                      ("ripe-rpki-validator-cache",),
                                                      mandatory=True,
                                                      default="ripe-rpki-validator-cache")
                        }
                    },
                    "rpki": {
                        "enabled": ValidatorBool(default=False),
                        "reject_invalid": ValidatorBool(mandatory=True,
                                                        default=True),
                    },
                    "max_prefix": {
                        "peering_db": {
                            "enabled": ValidatorBool(default=True),
                            "increment": {
                                "absolute": ValidatorUInt(default=100),
                                "relative": ValidatorUInt(default=15)
                            }
                        },
                        "general_limit_ipv4": ValidatorUInt(default=170000),
                        "general_limit_ipv6": ValidatorUInt(default=12000),
                        "action": ValidatorOption(
                            "action",
                            ("shutdown", "restart", "block", "warning"),
                            mandatory=False,
                            default="shutdown"
                        ),
                        "restart_after": ValidatorUInt(default=15,
                                                       mandatory=True)
                    },
                    "reject_policy": {
                        "policy": ValidatorOption("policy",
                                                  ("reject", "tag"),
                                                  default="reject")
                        },
                },
                "blackhole_filtering": {
                    "announce_to_client": ValidatorBool(
                        mandatory=True, default=True
                    ),
                    "policy_ipv4": ValidatorOption(
                        "policy_ipv4",
                        ("propagate-unchanged", "rewrite-next-hop"),
                        mandatory=False),
                    "policy_ipv6": ValidatorOption(
                        "policy_ipv6",
                        ("propagate-unchanged", "rewrite-next-hop"),
                        mandatory=False),
                    "rewrite_next_hop_ipv4": ValidatorIPv4Addr(mandatory=False),
                    "rewrite_next_hop_ipv6": ValidatorIPv6Addr(mandatory=False),
                    "add_noexport": ValidatorBool(default=True),
                },
                "graceful_shutdown": {
                    "enabled": ValidatorBool(mandatory=True, default=False),
                    "local_pref": ValidatorUInt(mandatory=True, default=0)
                },
                "rfc1997_wellknown_communities": {
                    "policy": ValidatorOption("policy", ("rfc1997", "pass"),
                                              default="pass"),
                },
                "rtt_thresholds": ValidatorRTTThresholds(mandatory=False),
                "communities": {
                },
                "custom_communities": {
                }
            }
        }

        if "rs_as" in self.cfg["cfg"]:
            rs_as_macro = self.cfg["cfg"]["rs_as"]
        else:
            rs_as_macro = None

        # Built-in communities validation schema
        for comm_tag in self.COMMUNITIES_SCHEMA:
            comm = self.COMMUNITIES_SCHEMA[comm_tag]
            peer_as = comm.get("peer_as", False)
            dyn_val = comm.get("dyn_val", False)

            schema["cfg"]["communities"][comm_tag] = self.new_community_validator(
                rs_as_macro, peer_as, dyn_val
            )

        # Custom communities validation schema
        if "custom_communities" in self.cfg["cfg"]:

            custom_comms = self.cfg["cfg"]["custom_communities"]
            if not isinstance(custom_comms, dict):
                raise ConfigError(
                    "The custom_communities section must be a dictionary."
                )

            for comm in custom_comms:
                # Add the validator for the custom community to the
                # validation schema.
                schema["cfg"]["custom_communities"][comm] = \
                    self.new_community_validator(rs_as_macro)

        try:
            # Convert next_hop_policy (< v0.6.0) into the new format
            convert_next_hop_policy(self.cfg["cfg"])

            # Convert max_prefix.peering_db (< v0.13.0) into the new format
            convert_maxprefix_peeringdb(self.cfg["cfg"])

            ConfigParserBase.validate(schema, self.cfg)
        except ARouteServerError as e:
            errors = True
            if str(e):
                logging.error(str(e))
            raise ConfigError()

        # Warning: missing global black list.
        if not self.cfg["cfg"]["filtering"].get("global_black_list_pref"):
            logging.warning("The 'filtering.global_black_list_pref' option is "
                            "missing or empty. It is strongly suggested to "
                            "provide at least the list of local IPv4/IPv6 "
                            "networks here.")

        # Warning: 'tag_as_set' is on but no communities are provided
        if self.cfg["cfg"]["filtering"]["irrdb"]["tag_as_set"]:
            tag_as_set_comms_found = False
            for comm in ("prefix_present_in_as_set",
                         "prefix_not_present_in_as_set",
                         "origin_present_in_as_set",
                         "origin_not_present_in_as_set"):
                for fmt in ("std", "ext", "lrg"):
                    if self.cfg["cfg"]["communities"][comm][fmt]:
                        tag_as_set_comms_found = True
                        break
                if tag_as_set_comms_found:
                    break
            if not tag_as_set_comms_found:
                logging.warning("The 'filtering.irrdb.tag_as_set' "
                                "option is set but no BGP communities "
                                "are provided to tag prefixes.")

        # If blackhole filtering policy = "rewrite-next-hop", then
        # blackhole next-hops must be provided.
        for ip_ver in (4, 6):
            bh = self.cfg["cfg"]["blackhole_filtering"]
            if not bh:
                continue
            policy = bh["policy_ipv{}".format(ip_ver)]
            if policy == "rewrite-next-hop":
                if not bh["rewrite_next_hop_ipv{}".format(ip_ver)]:
                    errors = True
                    logging.error(
                        "Since blackhole_filtering.policy_ipv{v} is "
                        "'rewrite_next_hop', an IPv{v} address must "
                        "be provided in "
                        "'rewrite_next_hop_ipv{v}'.".format(
                            v=ip_ver
                        )
                    )

        # Custom communities with same name of built-in communities?
        custom_comms = self.cfg["cfg"]["custom_communities"]
        for comm in custom_comms:
            if comm in schema["cfg"]["communities"]:
                errors = True
                logging.error("The custom community name '{}' collides "
                                "with a built-in community with the same "
                                "name.".format(comm))

        # Duplicate communities?
        unique_communities = []
        for comms in (self.cfg["cfg"]["communities"],
                      self.cfg["cfg"]["custom_communities"]):
            for comm_tag in sorted(comms):
                comm = comms[comm_tag]
                for fmt in ("std", "lrg", "ext"):
                    if comm[fmt]:
                        if comm[fmt] in unique_communities:
                            errors = True
                            logging.error(
                                "The '{}.{}' community's value ({}) "
                                "has already been used for another "
                                "community.".format(comm_tag, fmt, comm[fmt])
                            )
                        else:
                            unique_communities.append(comm[fmt])

        # The 'reject_cause' and 'rejected_route_announced_by' communities
        # can be set only if 'reject_policy' is 'tag'.
        if self.cfg["cfg"]["filtering"]["reject_policy"]["policy"] != "tag":
            for comm in ("reject_cause", "rejected_route_announced_by"):
                reject_comm_is_set = False
                for fmt in ("std", "ext", "lrg"):
                    if self.cfg["cfg"]["communities"][comm][fmt]:
                        reject_comm_is_set = True
                        break
                if reject_comm_is_set:
                    errors = True
                    logging.error(
                        "The '{}' community can be set only if "
                        "'reject_policy.policy' is 'tag'.".format(comm))

        # The 'reject_cause' comm is mandatory when 'reject_policy' is 'tag'.
        if self.cfg["cfg"]["filtering"]["reject_policy"]["policy"] == "tag":
            reject_comm_is_set = False
            for fmt in ("std", "ext", "lrg"):
                if self.cfg["cfg"]["communities"]["reject_cause"][fmt]:
                    reject_comm_is_set = True
                    break
            if not reject_comm_is_set:
                errors = True
                logging.error(
                    "The 'reject_cause' community must be configured when "
                    "'reject_policy.policy' is 'tag'.")

        # Overlapping communities?
        try:
            self.check_overlapping_communities()
        except ARouteServerError as e:
            errors = True
            if str(e):
                logging.error(str(e))

        # Are RTT-based functions used?
        self.rtt_based_functions_are_used = False
        for comm_name in self.cfg["cfg"]["communities"]:
            comm_schema = self.COMMUNITIES_SCHEMA[comm_name]
            if not comm_schema.get("rtt", False):
                continue

            comm = self.cfg["cfg"]["communities"][comm_name]
            if comm["std"] or comm["ext"] or comm["lrg"]:
                self.rtt_based_functions_are_used = True
                break

        # RTT-based functions are used: is RTT thresholds list set?
        if self.rtt_based_functions_are_used:
            if not self.cfg["cfg"]["rtt_thresholds"]:
                errors = True
                logging.error(
                    "Some RTT-based functions are configured but the "
                    "RTT thresholds list is empty."
                )

        if errors:
            raise ConfigError()

    def check_overlapping_communities(self, allow_private_asns=True):
        """Check if a 'dynamic' BGP community overlaps with others.

        This function is also called from whitin the OpenBGPD builder
        class. See remarks about 'allow_private_asns' below.

        Remember: dynamic values are allowed only in the last part of a
        community's value.

        Definitions of communities:
        - outbound c.   communities used by the route server to signal
                        something to its clients: origin_present_in_as_set,
                        prefix_present_in_as_set, custom communities, ...

        - inbound c.    communities sent by clients to the route server
                        to ask it to perform some action: blackholing,
                        do_something_to_peer, do_something_to_any, ...

        - internal c.   communities used internally by the route server;
                        they can't be neither accepted on routes entering
                        the server nor attached to routes leaving the server

        - peer_as c.    communities whose last part is a variable integer
                        that identifies the target ASN for which an action
                        is requested

        - dyn_val c.    communities whose last part is a variable integer
                        locally significant to the function the BGP community
                        is responsible for

        - dynamic c.    communities whose last part is a variable integer;
                        this is equal to 'peer_as' communities + 'dyn_val'
                        communities

        The 'dyn_val' 'internal' communities overlap with any other BGP
        community whose first part matches its first part.

        When a route leaves the route server, the route server scrubs any
        'inbound' community attached to it, so any 'outbound' community whose
        first part matches an 'inbound' 'peer_as' community would be deleted
        as well.

        Example:
        - inbound community "announce_to_peer" x:peer_as
        - outbound custom community "test" x:1

            route enters the rs: add "test" x:1
            route leaves the rs: delete "announce_to_peer" x:*
            the "test" community is removed

        The following corner-cases are allowed:
        - the 'peer_as' part doesn't collide with 'rs_as' part;
          a peer's ASN can't be the same of the route server one's
          example: 0:rs_as and 0:peer_as are fine.
        - the 'peer_as' part doesn't collide with 0;
          a peer's ASN can't be zero
          example: 65501:0 and 65501:peer_as are fine.

        The 'allow_private_asns' argument allows to add another case:
        - if allow_private_asns is True, the 'peer_as' part doesn't
          collide with private ASN ranges

        Example:
        - inbound community "announce_to_peer" x:peer_as
        - outbound custom community "test" x:65501

            route enters the rs: add "test" x:65501
            route leaves the rs: delete "announce_to_peer" x:[<64512]
            the "test" community is kept

        This argument can be set to True only when the route server is able
        to remove communities using numeric ranges, that is when it can scrub
        'peer_as' communities having the last part in the range of globally
        routable ASN only.
        In that case, any 'outbound' community whose first part matches an
        'inbound' 'peer_as' community and whose last part falls  within the
        private ASNs range would not be removed.
        Unfortunately, while BIRD allows this behaviour, OpenBGPD seems to be
        able to delete communities using wildcard only, and not ranges.

        This function is called from the config parser class with
        'allow_private_asns' set to True and also from OpenBGPD builder class
        with 'allow_private_asns' set to False.
        """

        def communities_overlap(comm1_tag, comm1, comm2_tag, comm2):
            rs_as = self.cfg["cfg"]["rs_as"]

            err_msg = ("Community '{comm1_tag}' and '{comm2_tag}' "
                       "overlap: {comm1_val} / {comm2_val}.")

            for fmt in ("std", "lrg", "ext"):
                if not comm1[fmt]:
                    continue
                if not comm2[fmt]:
                    continue
                comm1_val = comm1[fmt]
                comm2_val = comm2[fmt]
                comm1_parts = comm1_val.split(":")
                comm2_parts = comm2_val.split(":")
                for part_idx in range(len(comm1_parts)):
                    comm1_part = comm1_parts[part_idx]
                    comm2_part = comm2_parts[part_idx]
                    try:
                        # Remember: 'peer_as' and 'dyn_val' macros
                        # can be used only in the last part of a community,
                        # so if during the current 'for' iteration any of the
                        # two parts is one of these macros it means that the
                        # previous parts are already matching.

                        # If any of the two parts is 'dyn_val',
                        # the two communities are overlapping.
                        if comm1_part == "dyn_val" or \
                            comm2_part == "dyn_val":
                            raise ConfigError()

                        # the value that is not 'peer_as'
                        not_peer_as = None
                        if comm1_part == "peer_as":
                            not_peer_as = int(comm2_part)
                        if comm2_part == "peer_as":
                            not_peer_as = int(comm1_part)

                        # If none of the two communities use 'peer_as'
                        # they can't be overlapping.
                        # At most, they can be equal, but this is
                        # handled in a different place in the code.
                        if not_peer_as is not None:
                            if not_peer_as == rs_as:
                                continue
                            if not_peer_as == 0:
                                continue
                            if allow_private_asns:
                                if 64512 <= not_peer_as <= 65534:
                                    continue
                                if 4200000000 <= not_peer_as <= 4294967294:
                                    continue
                            raise ConfigError()
                    except ConfigError:
                        raise ConfigError(err_msg.format(
                            comm1_tag=comm1_tag, comm2_tag=comm2_tag,
                            comm1_val=comm1_val, comm2_val=comm2_val)
                        )
                    if comm1_part != comm2_part:
                        break

        def compare_communities(comms1, comms2, reason_text):
            for tag1 in sorted(comms1):
                for tag2 in sorted(comms2):
                    if tag1 == tag2:
                        continue
                    try:
                        communities_overlap(
                            tag1, comms1[tag1],
                            tag2, comms2[tag2]
                        )
                    except ConfigError as e:
                        logging.error(str(e) + " " + reason_text)
                        return False
            return True

        errors = False

        outbound_communities = {
            comm_name: self.cfg["cfg"]["communities"][comm_name]
            for comm_name in self.COMMUNITIES_SCHEMA
            if self.COMMUNITIES_SCHEMA[comm_name]["type"] == "outbound"
        }
        inbound_communities = {
            comm_name: self.cfg["cfg"]["communities"][comm_name]
            for comm_name in self.COMMUNITIES_SCHEMA
            if self.COMMUNITIES_SCHEMA[comm_name]["type"] == "inbound"
        }
        internal_communities = {
            comm_name: self.cfg["cfg"]["communities"][comm_name]
            for comm_name in self.COMMUNITIES_SCHEMA
            if self.COMMUNITIES_SCHEMA[comm_name]["type"] == "internal"
        }
        custom_communities = self.cfg["cfg"]["custom_communities"]

        errors = errors or not compare_communities(
            inbound_communities, outbound_communities,
            "Inbound communities and outbound communities "
            "can't have overlapping values, otherwise they "
            "might be scrubbed.")

        errors = errors or not compare_communities(
            inbound_communities, custom_communities,
            "Inbound communities and custom communities "
            "can't have overlapping values, otherwise they "
            "might be scrubbed.")

        errors = errors or not compare_communities(
            inbound_communities, inbound_communities,
            "Inbound communities can't have overlapping values, "
            "otherwise their meaning could be uncertain.")

        not_internal_communities = {}
        not_internal_communities.update(inbound_communities)
        not_internal_communities.update(outbound_communities)
        not_internal_communities.update(custom_communities)
        errors = errors or not compare_communities(
            internal_communities, not_internal_communities,
            "Internal communities can't have overlapping values with any "
            "other community.")

        if errors:
            raise ConfigError()

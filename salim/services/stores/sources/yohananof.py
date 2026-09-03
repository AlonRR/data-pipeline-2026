"""Yohananof — Cerberus portal, public account, no password."""
from __future__ import annotations

from sources.cerberus import CerberusStoreSource


class YohananofStoreSource(CerberusStoreSource):
    name = "yohananof"
    chain_id = "7290803800003"
    user_name = "yohananof"

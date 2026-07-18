from .cgi_repository import create_cgi_table, lookup_cgi
from .sdr_repository import create_sdr_table, lookup_mobile


def initialize_master_lookup_database() -> None:
    create_cgi_table()
    create_sdr_table()


def lookup_number_identity(number: str):
    return lookup_mobile(number)


def lookup_tower_address(cgi: str):
    return lookup_cgi(cgi)

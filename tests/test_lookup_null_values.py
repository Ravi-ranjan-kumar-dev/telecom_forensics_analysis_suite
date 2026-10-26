"""Missing pandas scalars must produce valid JSON on every lookup endpoint."""
import json
import math
import pandas as pd
import pytest


@pytest.mark.parametrize('missing',[None,float('nan'),pd.NA,pd.NaT])
def test_missing_values_on_single_and_batch_endpoints(monkeypatch,missing):
    from backend.app import schemas
    from backend.app.routers import lookup
    monkeypatch.setenv('ETHICALARMOR_MASTER_AUTHORITATIVE','1')
    sdr={field:missing for field in schemas.SDRProfileOut.model_fields}
    sdr.update(mobile_number='9876543210',subscriber_name='SYNTHETIC',raw_address=missing,clean_address='Fallback address',operator_or_source_category=missing,operator='Fallback operator')
    cgi={field:missing for field in schemas.CGIProfileOut.model_fields}
    cgi.update(cgi='405-01-11111')
    monkeypatch.setattr(lookup,'lookup_sdr_profile',lambda _:dict(found=True,record=sdr))
    monkeypatch.setattr(lookup,'lookup_cgi_profile',lambda _:dict(found=True,record=cgi))
    monkeypatch.setattr(lookup,'lookup_sdr_subscribers',lambda _:pd.DataFrame([{**sdr,'sdr_found':'YES','lookup_mobile':'9876543210','subscriber_address':missing}]))
    monkeypatch.setattr(lookup,'lookup_cgi_addresses',lambda _:pd.DataFrame([cgi]))
    single=lookup.lookup_sdr('9876543210',None,None)
    assert single.address=='Fallback address' and single.operator=='Fallback operator'
    outputs=[single,lookup.lookup_cgi('405-01-11111',None,None),lookup.lookup_sdr_batch(schemas.SDRBatchLookupRequest(numbers=['9876543210']),None,None),lookup.lookup_cgi_batch(schemas.CGIBatchLookupRequest(cgis=['405-01-11111']),None,None)]
    for output in outputs:
        parsed=json.loads(output.model_dump_json())
        encoded=json.dumps(parsed,allow_nan=False)
        assert 'NaN' not in encoded and '<NA>' not in encoded and 'NaT' not in encoded
    assert single.father_name is None
    assert outputs[2].records[0].father_name==''
    assert outputs[3].records[0].latitude is None


@pytest.mark.parametrize('coordinate',[float('inf'),-float('inf'),float('nan')])
def test_nonfinite_coordinates_are_json_null(coordinate):
    from backend.app.schemas import CGIProfileOut
    model=CGIProfileOut(cgi='405-01-11111',latitude=coordinate,longitude=coordinate)
    assert model.latitude is None and model.longitude is None

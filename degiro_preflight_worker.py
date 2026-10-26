"""Dedicated preview transport. No confirm, update, cancel or general SDK access."""
import json
import logging
import os
import re
import sys
from urllib.parse import urlsplit,parse_qs
from degiro_readonly_worker import login_diagnostic


def permitted(method,url):
    p = urlsplit(url)
    if p.scheme != 'https' or p.netloc != 'trader.degiro.nl' or p.fragment:
        return False
    return ((method == 'POST' and p.path in ('/login/secure/login','/login/secure/login/totp',
                '/product_search/secure/v5/products/info'))
        or (method == 'GET' and p.path in ('/pa/secure/client','/product_search/secure/v5/products/lookup'))
        or (method == 'POST' and re.fullmatch(r'/trading/secure/v5/checkOrder;jsessionid=[A-Za-z0-9._-]+',p.path) is not None)
        or (method == 'PUT' and re.fullmatch(r'/trading/secure/logout;jsessionid=[A-Za-z0-9._-]+',p.path) is not None))


def run(payload):
    from degiro_preflight import validate
    payload = validate(payload)
    logging.disable(logging.CRITICAL)
    import requests
    from degiro_connector.trading.api import API
    from degiro_connector.trading.models.credentials import Credentials
    from degiro_connector.trading.models.product_search import LookupRequest
    from degiro_connector.trading.models.order import Order,Action,OrderType,TimeType
    from degiro_connector.core.models.model_session import ModelSession
    from degiro_connector.core.models.model_connection import ModelConnection
    login_reason, check_status, expected, check_count = None,None,None,0

    class PreviewSession(requests.Session):
        def send(self,request,**kwargs):
            nonlocal login_reason,check_status,check_count
            if not permitted(request.method,request.url):
                raise ValueError('Preview transport rejected request')
            p = urlsplit(request.url)
            if '/checkOrder;' in p.path:
                if check_count or expected is None or json.loads(request.body) != expected:
                    raise ValueError('Preview body mismatch or repeated attempt')
                check_count += 1
            if p.path.endswith('/products/lookup'):
                q = parse_qs(p.query)
                if q.get('searchText') != [payload['isin']] or q.get('limit') != ['20']:
                    raise ValueError('Unexpected lookup')
            kwargs.update(timeout=(5,8),allow_redirects=False)
            response = super().send(request,**kwargs)
            if '/login/secure/login' in p.path:
                login_reason = login_diagnostic(response)
            if '/checkOrder;' in p.path:
                check_status = response.status_code
            return response

    credentials = Credentials(username=os.environ['BOB_DEGIRO_USERNAME'],password=os.environ['BOB_DEGIRO_PASSWORD'])
    if payload['otp']:
        credentials.one_time_password = payload['otp']
    connection = ModelConnection(timeout=60)
    storage = ModelSession(hooks=connection.build_hooks())
    session = PreviewSession(); session.trust_env = False
    connection.setup_hooks(session);storage.session=session
    api = API(credentials=credentials,connection_storage=connection,session_storage=storage,preload=False)
    result = {'code':'SDK_ERROR','logoutConfirmed':False}
    try:
        api.connect()
        if login_reason:
            result.update(code='AUTH_REQUIRED',authReason=login_reason)
            return result
        details = api.get_client_details()
        account = details.get('data',{}).get('intAccount') if isinstance(details,dict) else None
        if type(account) is not int or account <= 0:
            return result
        credentials.int_account = account
        found = api.product_search(product_request=LookupRequest(search_text=payload['isin'],limit=20,offset=0),raw=True)
        rows = found.get('products') if isinstance(found,dict) else None
        matches = [x for x in rows if isinstance(x,dict) and x.get('isin')==payload['isin'] and x.get('currency')==payload['currency']] if isinstance(rows,list) else []
        if len(matches)!=1 or not re.fullmatch(r'[1-9][0-9]{0,15}',str(matches[0].get('id',''))):
            result['code']='IDENTITY_UNCONFIRMED';return result
        pid = int(matches[0]['id'])
        info = api.get_products_info(product_list=[pid],raw=True)
        product = info.get('data',{}).get(str(pid)) if isinstance(info,dict) else None
        if not isinstance(product,dict) or str(product.get('id'))!=str(pid) or product.get('isin')!=payload['isin'] or product.get('currency')!=payload['currency']:
            result['code']='IDENTITY_UNCONFIRMED';return result
        order = Order(buy_sell=Action.BUY if payload['side']=='BUY' else Action.SELL,
            order_type=OrderType.LIMIT,product_id=pid,size=payload['quantity'],price=payload['price'],time_type=TimeType.GOOD_TILL_DAY)
        expected = {'buySell':payload['side'],'orderType':0,'productId':pid,
                    'size':payload['quantity'],'price':payload['price'],'timeType':1}
        response = api.check_order(order=order,raw=True)
        data = response.get('data') if isinstance(response,dict) else None
        # Only evidence that the broker returned a preview token. Never an
        # execution/eligibility guarantee; never return or persist that token.
        token = data.get('confirmationId') if isinstance(data,dict) else None
        result['code'] = ('PRECHECK_RESPONSE' if check_status==200 and isinstance(token,str) and 0<len(token)<=256
                          and not response.get('errors') and not response.get('error') else
                          'BROKER_REJECTED' if check_status==400 else 'UNVERIFIED_RESPONSE')
    except Exception:
        if login_reason:
            result.update(code='AUTH_REQUIRED',authReason=login_reason)
    finally:
        if connection.connected.is_set():
            try: result['logoutConfirmed']=api.logout() is True
            except Exception: pass
        session.close()
    return result


if __name__=='__main__':
    try: result=run(json.loads(sys.stdin.read(2048)))
    except Exception: result={'code':'SDK_ERROR','logoutConfirmed':False}
    print(json.dumps(result))

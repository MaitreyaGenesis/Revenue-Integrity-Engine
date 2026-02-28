from simple_salesforce.api import Salesforce

def get_salesforce_client(username, password, security_token):
    return Salesforce(
        username=username,
        password=password,
        security_token=security_token
    )

def run_query(sf, query: str):
    return sf.query_all(query)["records"]

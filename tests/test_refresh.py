from time import sleep
from insightclient import InsightClient


# Test token refresh logic, for this test to function, clients need to have a
# access_token expirity of 1 second
def test_refresh():
    client = InsightClient()

    client.get_inodes()
    sleep(1)

    client.get_inodes()

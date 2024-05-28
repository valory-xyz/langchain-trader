# Langchain trader

An [Olas](https://olas.network/) agent that makes transactions on the Gnosis chain.

## System requirements

- Python `>=3.10`
- [Tendermint](https://docs.tendermint.com/v0.34/introduction/install.html) `==0.34.19`
- [IPFS node](https://docs.ipfs.io/install/command-line/#official-distributions) `==0.6.0`
- [Pip](https://pip.pypa.io/en/stable/installation/)
- [Poetry](https://python-poetry.org/)
- [Docker Engine](https://docs.docker.com/engine/install/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [Set Docker permissions so you can run containers as non-root user](https://docs.docker.com/engine/install/linux-postinstall/)


## Run you own agent

### Get the code

1. Clone this repo:

    ```
    git clone git@github.com:valory-xyz/langchain-trader.git
    ```

2. Create the virtual environment:

    ```
    cd langchain-trader
    poetry shell
    poetry install
    ```

3. Sync packages:

    ```
    autonomy packages sync --update-packages
    ```

### Prepare the data

1. Prepare a keys.json file containing wallet address and the private key for each of the agents. To create this file, either generate a new one with `autonomy generate-key ethereum -n 1` or export a existing one using Metamask and follow the following format:

    ```
    [
        {
            "address": "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
            "private_key": "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a"
        }
    ]
    ```

2. Deploy a [Safe on Gnosis](https://app.safe.global/welcome) and set your agent address as one of the signers.

3. Fund both your agent and Safe with a small amount of xDAI, i.e. $0.05 each.


### Run the service

1. Make a copy of the env file:

    ```
    cp sample.env .env
    ```

2. Fill in the required environment variables in .env. You'll need a Ethereum RPC even if the service runs on Gnosis. These variables are: `ALL_PARTICIPANTS`, `ETHEREUM_LEDGER_RPC`, `GNOSIS_LEDGER_RPC` and `SAFE_CONTRACT_ADDRESS`.

3. Check that Docker is running:

    ```
    docker
    ```

4. Run the service:

    ```
    bash run_service.sh
    ```

5. Look at the service logs (on another terminal):

    ```
    docker logs -f langchaintrader_abci_0
    ```

6. Make a request:

    ```
    curl -X POST http://localhost:8000/request -H "Content-Type: application/json" -d '{"prompt":"Will Apple unveil a new Iphone before the end of 2024?"}'
    ```
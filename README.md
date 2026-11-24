# Solar Chain
![](public%2Fstatic%2FResources%2FScreenshots%2Fimg.png)
*A Peer-to-Peer Energy Trading Platform*

# Table of Contents
- [About](#about)
- [Project Structure](#project-structure)
- [Setup](#setup)
- [Running the Program](#running-the-program)
- [Common Issues](#common-issues)
- [Tools Used](#tools-used)

# About
This project enables a decentralized platform for trading surplus solar energy using blockchain technology. Our solution empowers individuals and businesses to take full control of their surplus energy. We’re building a future where clean energy is accessible, affordable, and efficient for everyone.

Our platform ensures transparency, security, and efficiency using blockchain technology.
![blockchain.png](public%2Fstatic%2FResources%2Fimages%2Fblockchain.png)

# Project demonstration

https://github.com/user-attachments/assets/db471aab-fb2c-4275-aa5f-2092dedd6da2

# Project Structure

## Directories
- [*doc*](doc): Documentations
- [*instance*](instance): Database location and other files 
- [*public/static*](public/static): CSS, JavaScript, images and videos served by Vercel's CDN or Flask locally
- [*main*](main):  Contains all the main scripts
  - [*templates*](main/templates): HTML webpages
- [*tests*](tests): Contain all the tests for our project
- [*util*](util): Helpful tools
- [*playground*](playground): Standalone testing before full implementation. See [Smart Contract Run Example](playground/basic_transfer.py) and [Asset Creation](playground/asset_creation.py) file
- [*Solar Chain*](SolarChain/projects/SolarChain): Algokit Project containing the [Smart Contract](SolarChain/projects/SolarChain/smart_contracts/unit_transfer/unit_contract.py)

# Setup

### Pre-requisites

- [Python 3.12](https://www.python.org/downloads/) or later
- [Docker](https://www.docker.com/) (only required for LocalNet)
- Make sure all packages are installed.
  - Run `pip install -r requirements.txt` to install all required packages.
- For compiling contract after modification run: `algokit compile py <INPUT> --output-arc32 --no-output-teal`. *No need to run this if contract is not modified.*

### Initial Setup

#### 1. Clone the Repository
Start by cloning this repository to your local machine.

#### 2. Install Pre-requisites
Ensure the following pre-requisites are installed and properly configured:

- **Docker**: Required for running a local Algorand network. [Install Docker](https://www.docker.com/).
- **AlgoKit CLI**: Essential for project setup and operations. Install the latest version from [AlgoKit CLI Installation Guide](https://github.com/algorandfoundation/algokit-cli#install). Verify installation with `algokit --version`, expecting `2.5.0` or later.
- **Start LocalNet**: Use `algokit localnet start` to initiate a local Algorand network.

> For test net just run [this file](playground/basic_transfer.py) and make sure the variable `LOCAL_NET` is set to false and accounts are properly setup in the [accounts file](account_constants.py).

> Pycharm was the IDE used.

# Running the program.
Run [`app.py`](app.py) and navigate to the [website](http://127.0.0.1:5000/).

For standalone smart contract testing navigate to [Standalone file](playground/basic_transfer.py)
> NOTE: If using localnet you will have to create new localnet accounts and asset for testing on localnet. If doing so then mention the new accounts' mnemonic in [this file](account_constants.py) in the `ACCOUNTS_LOCAL` list and update the `ASSET_ID_LOCAL_NET` variable to the new asset's ID. See [this file](playground/asset_creation.py) to create a new asset for localnet.
>
> For using test net make sure that in the file the variable `LOCAL_NET` is set to false. This will make it automatically use the testnet accounts mentioned in the [accounts file](account_constants.py).

# Common Issues
## Docker Errors
Logged in but got `unauthorized: incorrect username or password error.`

Right-Click on the system tray icon, does it show you logged in as username@domain.com? If so, Sign out, the issue is that you must login to Docker using your hub username, which is different than your email address, even though in some cases, both are interchangeable.
You can do this by signing out from the system tray icon, or by logging in at a command prompt, using the syntax `docker login --username your_username_here.`
If you’re not sure of your username, you can login to the [Docker Hub](https://hub.docker.com/), and your username will be displayed on the far right hand side of the menu bar, next to “Dashboard”, “Explore” and such.

# Tools Used

This project makes use of Algorand Python to build Algorand smart contracts.

The following tools are in use:

- [AlgoKit](https://github.com/algorandfoundation/algokit-cli) - One-stop shop tool for developers building on the Algorand network; [docs](https://github.com/algorandfoundation/algokit-cli/blob/main/docs/algokit.md), [intro tutorial](https://github.com/algorandfoundation/algokit-cli/blob/main/docs/tutorials/intro.md)
- [Algorand Python](https://github.com/algorandfoundation/puya) - A semantically and syntactically compatible, typed Python language that works with standard Python tooling and allows you to express smart contracts (apps) and smart signatures (logic signatures) for deployment on the Algorand Virtual Machine (AVM); [docs](https://github.com/algorandfoundation/puya), [examples](https://github.com/algorandfoundation/puya/tree/main/examples)
- [AlgoKit Utils](https://github.com/algorandfoundation/algokit-utils-py) - A set of core Algorand utilities that make it easier to build solutions on Algorand.
- [pytest](https://docs.pytest.org/): Automated testing.
- [Docker](https://www.docker.com/): For localnet testing
- [Flask](https://flask.palletsprojects.com/en/stable/): For backend

Contributions are welcome—check out our code and join us in revolutionizing energy sharing!

# Deploy the website to Vercel

Deploy the root Flask application (app.py) from branch `algo-show`. The nested
`SolarChain/projects/SolarChain` directory contains contract development tools;
it is not a second web service.

1. Create a PostgreSQL database in [Neon](https://neon.tech) (or connect Neon through
   the [Vercel Marketplace](https://vercel.com/docs/postgres)). Copy its pooled
   connection string, including the SSL query parameters.
2. Import the GitHub repository in Vercel. Select **Import single project** for
   **app / Flask**, root directory **./**, and the **Flask** framework preset.
   Use **algo-show** as the production branch
   (Settings > Environments > Production > Branch Tracking).
3. Set **DATABASE_URL** to the Neon connection string and **SECRET_KEY** to a
   random secret in Vercel's environment variables. Generate a secret locally with:
   `py -3.12 -c "import secrets; print(secrets.token_hex(32))"`.
   Add the values to the environments you intend to deploy.
4. Leave install/output overrides unset. The committed `vercel.json` selects
   Flask. Assets are committed in `public/static` and served at their existing
   `/static/...` URLs without a build copy. Deploy (or redeploy after setting variables).
5. Open the deployed URL and register an account. Missing tables are created
   automatically. The hosted database starts empty: this does not upload or migrate
   the local `instance/main.db` file.

Accounts, listings, trade history, and purchase status use PostgreSQL and survive
redeployments. Local runs still use SQLite when DATABASE_URL is unset. Environment
files are examples only; export variables in your shell or set them in Vercel.

Vercel purchases finish blockchain work within the request, with a 300-second
function limit. This is a simple deployment, not a durable job queue: timeouts
still need investigation rather than blindly retrying a trade. Existing behavior
records energy changes before blockchain confirmation; a failed on-chain write
does not roll those changes back. Real TestNet purchases still require the
accounts and asset in `account_constants.py` to be valid and funded.
Arduino connections remain in process memory and are not coordinated across
Vercel instances; use the local server for the hardware demonstration.

The original toolchain is preserved in `requirements-dev.txt`.
Deployment tests (mocked blockchain; isolated SQLite, not a live Neon database):
`python -m pytest tests/test_web_deployment.py -q`.

Reference: [Flask on Vercel](https://vercel.com/docs/frameworks/backend/flask).

# 1. Crie o ambiente virtual (.venv)

python -m venv .venv

# 2. Ative o ambiente virtual

.venv\Scripts\Activate.ps1

# 3. Instale as bibliotecas necessárias

pip install -r requirements.txt

# 4. Crie seu .env a partir do template

copy .env.example .env

# 5. Execute o painel

streamlit run app.py --server.port 8502

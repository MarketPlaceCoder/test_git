# Open Research PWA (Free Sources Only)

This project lives in a folder named **test_git**. The frontend is in **docs/** so GitHub Pages can serve it over HTTPS. The backend is a FastAPI app in **backend/**.

- Frontend live path on GitHub Pages (project site): `https://<username>.github.io/<repo>/`
- If your repo is named `test_git`, that path is: `https://<username>.github.io/test_git/`

## 1) Run locally (Mac/Linux/Windows)

### Backend
```bash
cd backend
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000 --reload


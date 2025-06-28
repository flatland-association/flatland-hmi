# Agentic Chatbot Interface

An agentic chatbot interfaces.

> ⚠️ **Important!** 
>
> The prompts are not yet fully tuned and may malfunction or produce unexpected results.

https://github.com/user-attachments/assets/57a51fcb-fbf2-40ee-a582-d8f4fdf8bcc0

## TODOs
- Add frontend code
- Tune prompts
- Add tests
- docker-compose setup for backend and frontend

## Backend

Implemented via flask-api and langraph framwork.

### Structure
- `llm_agent/api/`: Contains the Flask API implementation.
- `llm_agent/src/`: Contains the flatland_agent package for the agentic chatbot logic.

### Setup

1. Install dependencies and flatland_agent package using Poetry:
    ```bash
    cd llm_agent
    poetry install
    ```

2. Create a `.env` file in the `llm_agent` directory with the env variables as described in the `sample.env` file.

3. Run the application:
    ```bash
    cd llm_agent
    poetry run python api/main.py
    ```

4. Access the API endpoint at `http://localhost:8000/prompt`

## Frontend

**TODO**: add frontend code
The frontend is implemented with assistant-ai.

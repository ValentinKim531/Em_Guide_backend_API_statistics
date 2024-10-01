from fastapi import FastAPI, HTTPException, Depends, WebSocketDisconnect
import logging
from pydantic import BaseModel
from starlette.websockets import WebSocket
from crud import Postgres
from statistics_service import generate_statistics_file, verify_token_with_auth_server, save_statistics_to_excel
from database import async_session
from fastapi.middleware.cors import CORSMiddleware
import json
import pandas as pd

app = FastAPI()

# Настройки CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешить запросы с любых источников
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)


class StatsRequest(BaseModel):
    token: str
    action: str
    type: str


db = Postgres(async_session)


# Создание зависимости для базы данных
def get_database() -> Postgres:
    return Postgres(async_session)


@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()  # Получаем сообщение от клиента
            logger.info(f"Received data: {data}")

            # Преобразуем строку JSON в словарь
            request_data = json.loads(data)
            token = request_data.get("token")
            action = request_data.get("action")
            request_type = request_data.get("type")

            # Проверяем действие и тип запроса
            if action == "export_stats" and request_type == "command":
                user_data = await verify_token_with_auth_server(token)
                if not user_data or 'result' not in user_data or 'phone' not in user_data['result']:
                    error_response = {
                        "type": "response",
                        "status": "error",
                        "error": "invalid_token",
                        "message": "Invalid or expired JWT token. Please re-authenticate.",
                    }
                    await websocket.send_text(json.dumps(error_response))
                    continue

                user_id = user_data['result']['phone']

                # Генерация статистики
                stats = await generate_statistics_file(user_id, db)


                if not stats:
                    error_response = {
                        "type": "response",
                        "status": "error",
                        "action": "export_stats",
                        "error": "no_stats",
                        "message": "No stats available.",
                    }
                    await websocket.send_text(json.dumps(error_response))
                    continue

                # Конвертация `Timestamp` в строки для JSON
                for month, records in stats["statistics"].items():
                    for record in records:
                        record["Дата создания"] = pd.to_datetime(record["Дата создания"]).strftime("%Y-%m-%dT%H:%M:%S")
                        record["Дата обновления"] = pd.to_datetime(record["Дата обновления"]).strftime(
                            "%Y-%m-%dT%H:%M:%S")

                # Возвращаем статистику в формате JSON
                response = {
                    "type": "response",
                    "status": "success",
                    "action": "export_stats",
                    "data": {"file_json": stats},
                }
                await websocket.send_text(json.dumps(response, ensure_ascii=False))
                # await save_statistics_to_excel(stats)
            else:
                error_response = {
                    "type": "response",
                    "status": "error",
                    "message": "Invalid action or type."
                }
                await websocket.send_text(json.dumps(error_response))


    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Error handling websocket: {e}")
        await websocket.close()


@app.post("/get-stat")
async def get_stat(request: StatsRequest, database: Postgres = Depends(get_database)):
    if request.action != "export_stats" or request.type != "command":
        raise HTTPException(status_code=400, detail="Invalid action or type")

    user_data = await verify_token_with_auth_server(request.token)
    if not user_data or 'result' not in user_data or 'phone' not in user_data['result']:
        return {
            "type": "response",
            "status": "error",
            "error": "invalid_token",
            "message": "Invalid or expired JWT token. Please re-authenticate.",
        }

    user_id = user_data['result']['phone']

    try:
        # Генерация статистики
        stats = await generate_statistics_file(user_id, database)

        if not stats:
            return {
                "type": "response",
                "status": "error",
                "action": "export_stats",
                "error": "no_stats",
                "message": "No stats available.",
            }

        # Опционально сохраняем статистику в Excel
        await save_statistics_to_excel(stats)

        return {
            "type": "response",
            "status": "success",
            "action": "export_stats",
            "data": {"file_json": stats},
        }
    except Exception as e:
        logger.error(f"Error generating export stats: {e}")
        return {
            "type": "response",
            "status": "error",
            "action": "export_stats",
            "error": "server_error",
            "message": "An internal server error occurred. Please try again later.",
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8084)

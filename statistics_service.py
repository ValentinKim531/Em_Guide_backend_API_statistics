from datetime import datetime
import logging
from io import BytesIO
import pandas as pd
from crud import Postgres
from models import Survey
import httpx
from babel.dates import format_date



logger = logging.getLogger(__name__)

async def verify_token_with_auth_server(token):
    try:
        url = "https://backoffice.daribar.com/api/v1/users"
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                logger.info(f"responseJWT: {response.json()}")
                return response.json()
            else:
                return None
    except Exception as e:
        logger.error(f"Error verifying token: {e}")
        return None


async def generate_statistics_file(user_id, db: Postgres):
    """
    Генерация статистики по пользователю и возврат в формате JSON для фронта.
    """
    try:
        logger.info(f"Fetching statistics for user_id: {user_id}")

        # Получение данных опросов пользователя
        user_records = await db.get_entities_parameter(Survey, {"userid": user_id})

        if not user_records:
            logger.info(f"No records found for user {user_id}")
            return None

        # Логирование количества найденных записей
        logger.info(f"Found {len(user_records)} records for user {user_id}")

        # Подготовка данных для DataFrame
        data = [
            {
                "Номер": str(record.survey_id),
                "Дата создания": record.created_at.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "Дата обновления": record.updated_at.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "Головная боль сегодня": record.headache_today,
                "Принимали ли медикаменты": record.medicament_today,
                "Интенсивность боли": record.pain_intensity,
                "Область боли": record.pain_area,
                "Детали области": record.area_detail,
                "Тип боли": record.pain_type,
                "Комментарии": record.comments,
            }
            for record in user_records
        ]

        # Создание DataFrame для данных опросов
        df_records = pd.DataFrame(data)

        # Преобразуем дату без учета временной зоны, чтобы избежать предупреждений
        df_records["Дата создания"] = pd.to_datetime(df_records["Дата создания"]).dt.tz_localize(None)

        # Группируем данные по месяцам для удобного отображения
        months = df_records["Дата создания"].dt.to_period("M").sort_values(ascending=False).unique()

        grouped_data = {}
        for month in months:
            month_data = df_records[df_records["Дата создания"].dt.to_period("M") == month]
            grouped_data[month.strftime("%Y-%m")] = month_data.to_dict(orient="records")

        # Формируем итоговый результат с данными по пользователю
        result = {
            "phone_number": user_id,
            "statistics": grouped_data
        }

        return result

    except Exception as e:
        logger.error(f"Error generating statistics file for user {user_id}: {e}")
        return None


def convert_timestamps(data):
    """
    Преобразует все временные метки в строковый формат для корректного отображения в JSON и Excel.
    """
    for record in data:
        if 'Дата создания' in record and isinstance(record['Дата создания'], datetime):
            record['Дата создания'] = record['Дата создания'].strftime("%Y-%m-%dT%H:%M:%S")
        if 'Дата обновления' in record and isinstance(record['Дата обновления'], datetime):
            record['Дата обновления'] = record['Дата обновления'].strftime("%Y-%m-%dT%H:%M:%S")
    return data


async def save_statistics_to_excel(statistics_data):
    """
    Опциональная функция для сохранения данных в Excel.
    """
    try:
        # Создаём пустой Excel файл
        excel_buffer = BytesIO()

        # Открываем Excel writer с помощью Pandas
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            # Извлекаем номер телефона
            phone_number = statistics_data.get('phone_number', 'N/A')

            # Получаем данные статистики
            statistics = statistics_data.get('statistics', {})

            # Создаем заголовок с номером телефона
            df_phone = pd.DataFrame({'Phone Number': [phone_number]})
            df_phone.to_excel(writer, sheet_name='Statistics', index=False, startrow=0)

            # Получаем объект workbook для форматирования
            workbook = writer.book
            worksheet = writer.sheets['Statistics']

            # Формат для заголовков
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#F7DC6F',
                'border': 1
            })

            # Стартовая строка для статистики
            start_row = 2

            # Проходим по месяцам
            for month, records in statistics.items():
                # Преобразуем временные метки в строковый формат
                records = convert_timestamps(records)

                # Форматируем месяц и год в заголовок
                if records and 'Дата создания' in records[0]:
                    try:
                        month_date = pd.to_datetime(records[0]['Дата создания'])
                        month_name = format_date(month_date, "LLLL yyyy", locale="ru")
                        logger.info(f"month_name: {month_name}")

                        # Добавляем заголовок месяца и года
                        worksheet.write(start_row, 0, f"Месяц: {month_name}")
                        start_row += 1
                    except Exception as e:
                        logger.error(f"Error formatting month and year: {e}")
                else:
                    logger.warning("No 'Дата создания' found in records.")

                # Преобразуем записи за этот месяц в DataFrame
                df_records = pd.DataFrame(records)
                df_records.to_excel(writer, sheet_name='Statistics', index=False, startrow=start_row)

                # Применяем форматирование заголовков
                for col_num, value in enumerate(df_records.columns.values):
                    worksheet.write(start_row, col_num, value, header_format)

                # Обновляем стартовую строку для следующего месяца
                start_row += len(df_records) + 2

        # Сохраняем Excel файл
        excel_buffer.seek(0)
        excel_file_path = 'statistics_output.xlsx'
        with open(excel_file_path, 'wb') as f:
            f.write(excel_buffer.getvalue())

        return excel_file_path
    except Exception as e:
        logger.error(f"Error saving JSON to Excel: {e}")
        return None
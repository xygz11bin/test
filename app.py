import os
import sys
import yaml
import shutil
import logging
import logging.handlers
from flask import Flask, request, send_file, abort, render_template,jsonify,flash, redirect, url_for, send_from_directory
from threading import Thread
from time import sleep
from datetime import datetime
import pyodbc
import schedule
import time
import calendar
import csv
import json
import uuid
import pandas as pd
from io import BytesIO
from io import StringIO
from flask import make_response

app = Flask(__name__)

def load_config():
    """加载外部的 YAML 配置文件"""
    # 获取当前可执行文件的路径或脚本路径
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe
        base_path = os.path.dirname(sys.executable)
    else:
        # 如果是直接运行的脚本
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    config_path = os.path.join(base_path, 'config.yaml')
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)

config = load_config()
app.secret_key = 'some_secret_key'
user = config['SqlBase']['Username']
password = config['SqlBase']['PW']
IC = config['SqlBase']['IC']
IP = config['SqlBase']['IP']
Table = config['SqlBase']['Table']

# 创建日志记录器
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 创建日志文件处理器
file_handler = logging.FileHandler('backup.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(message)s'))

# 如果之前已经有处理器，先清空处理器，避免重复日志
if logger.hasHandlers():
    logger.handlers.clear()

# 将处理器添加到日志记录器
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# 确保 Flask 使用同一个日志记录器
app.logger.handlers = logger.handlers
app.logger.setLevel(logging.INFO)

#备份历史文件
def backup_files():
    try:
        src = config['paths']['file_api']
        file_directory = config['paths']['file_directory']
        backup_directory = config['paths']['file_backup']
        dest = config['paths']['file_download']

        for filename in os.listdir(src):
            src_file = os.path.join(src, filename)
            if filename.startswith("plist") and filename.endswith(".csv"):
                dest_file = os.path.join(dest, "plist.csv")
                version_file = os.path.join(dest, "version.txt")
            else:
                dest_file = os.path.join(dest, filename)
                version_file = None

            if os.path.isfile(src_file):
                if os.path.exists(dest_file):
                    os.remove(dest_file)
                shutil.copy2(src_file, dest_file)
                logging.info(f"从备份文件夹复制文件: {src_file} 到 {dest_file}")

                if version_file:
                    with open(version_file, 'w') as vf:
                        vf.write(filename)
                    logging.info(f"写入原始文件名到 {version_file}: {filename}")

        # 创建备份目录
        os.makedirs(backup_directory, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_directory, f"backup_{timestamp}")
        shutil.copytree(file_directory, backup_path)
        logging.info(f"Backup created at {backup_path}")

    except Exception as e:
        logging.error(f"Failed to create backup: {str(e)}")

def connect_to_db():
    """Connect to MSSQL database."""

    connection = pyodbc.connect("DRIVER={SQL Server};User ID="+user+";Password="+password+";Initial Catalog="+IC+";Server="+IP)
    return connection

def convert_to_week_format(date_str):
    """将 '年-月-日' 的时间字符串转换为 '24W22' 的格式."""
    try:
        # 将 '年-月-日' 格式转换为 datetime 对象
        #date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        # 获取当前时间
        #date_obj =datetime.now().strptime('%Y-%m-%d  %H:%M:%S')
        date_obj = datetime.now()

        year=str(date_obj.year)[-2:]
        # 获取年份的最后两位数
        #year = date_obj.strftime("%Y")

        # 计算周数
        week_number = date_obj.isocalendar()[1]
        if week_number<10:
            sweek_number='0'+str(week_number)
        elif week_number>=10:
            sweek_number=str(week_number)
        # 返回 '24W22' 格式
        return f"{year}W"+sweek_number
    except Exception as e:
        print(f"Error converting date: {str(e)}")
        return None
# 查询WorkOrderNo=X的条目
@app.route('/get_order', methods=['GET'])
def get_order():
    # 从请求中获取 order 参数
    try:
        order = request.args.get('order')
        
        # 检查是否提供了 order 参数
        if not order:
            logging.error(f"'error': 'Order not found'")
            return jsonify({'error': 'No order number provided'}), 400

        # 查询数据库
        conn = connect_to_db()
        cursor = conn.cursor()
        
        # 查询SQL
        query = f"""
            SELECT
                [ProductLine], 
                [ProductModel], 
                [ProductNumber], 
                [ProductItem], 
                [tpCode], 
                [BarCode], 
                [ProductPlanLine], 
                [WorkOrderNo], 
                [PlanDate],
                [TestValue1],
                [TestValue2],
                [MSN],
                [PSN],
                [GXzt] 
            FROM [{Table}].[dbo].[SCPlan] 
            WHERE WorkOrderNo = ?
        """
        
        # 执行查询
        cursor.execute(query, order)
        
        # 获取查询结果
        row = cursor.fetchone()
        query = """
            SELECT COUNT(*)  
            FROM [bosch].[dbo].[SCPlan]   
            WHERE WorkOrderNo  = ?
        """
        cursor.execute(query, order)
        result = cursor.fetchone()
        if row:
            # 将结果转换为字典
            result = {
                'Count': result[0],
                'ProductLine': row.ProductLine,
                'ProductModel': row.ProductModel,
                'ProductNumber': row.ProductNumber,
                'ProductItem': row.ProductItem,
                'tpCode': row.tpCode,
                'BarCode': row.BarCode,
                'ProductPlanLine': row.ProductPlanLine,
                'WorkOrderNo': row.WorkOrderNo,
                'PlanDate': row.PlanDate,
                'ProductWeek': convert_to_week_format(row.PlanDate),
                'TestValue1':row.TestValue1,
                'TestValue2':row.TestValue2,
                'MSN':row.MSN,
                'PSN':row.PSN,
                'GXzt':row.GXzt,
                'error':''
            }
            return jsonify(result)
            logging.info(f"get the order number {row.WorkOrderNo}'")
        else:
            logging.error(f"'error': 'Order not found'")
            return jsonify({'error': 'Order not found'}), 404

        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to get_order: {str(e)}")
        return jsonify({'error': 'Failed to get_order'}), 404
# GetSn 功能：查找 WorkOrderNo 对应的条目
@app.route('/get_sn', methods=['GET'])
def get_sn():
    # 从请求中获取 GetSn 参数
    try:
        work_order_no = request.args.get('GetSn')

        # 检查是否提供了 GetSn 参数
        if not work_order_no:
            logging.error(f"error': 'No WorkOrderNo provided")
            return jsonify({'error': 'No WorkOrderNo provided'}), 400

        conn = connect_to_db()
        cursor = conn.cursor()

        # 1. 先查询 [CtrlxIO_Production_New] 表中是否有符合条件的记录
        query_new = f"""
            SELECT TOP 1 * FROM [{Table}].[dbo].[CtrlxIO_Production]
            WHERE [WorkOrderNo] = ? AND [LaserStatus] IS NULL
        """
        cursor.execute(query_new, work_order_no) 
        row_new = cursor.fetchone()

        if row_new:
            # 如果找到了符合条件的记录，返回该记录
            result = {
                'WorkOrderNo': row_new.WorkOrderNo,
                'ProductSN': row_new.ProductSN,
                'ProductLine': row_new.ProductLine,
                'ProductWeek': convert_to_week_format(row_new.PlanDate),
                'ProductModel': row_new.ProductModel,
                'ProductNumber': row_new.ProductNumber,
                'ProductItem': row_new.ProductItem,
                'tpCode': row_new.tpCode,
                'BarCode': row_new.BarCode,
                'ProductPlanLine': row_new.ProductPlanLine,
                'PlanDate': row_new.PlanDate,
                'MSN':row_new.MSN,
                'PSN':row_new.PSN,
                'GXzt':row_new.GXzt,
                'TestValue1':row_new.TestValue1,
                'TestValue2':row_new.TestValue2,
                'error':''
            }

            # 1. 查询并更新 tpCode=X 对应的记录，将 BarCode 设置为 Y，LaserStatus 设置为 'finished'
            query_update = f"""
                UPDATE [{Table}].[dbo].[CtrlxIO_Production]
                SET [ProductWeek] = ?
                WHERE [ProductSN] = ?
            """

            # 执行更新操作
            cursor.execute(query_update,convert_to_week_format(row_new.PlanDate),row_new.ProductSN)
            conn.commit()
            cursor.close()
            conn.close()
            logging.info(f"message': 'get sn {row_new.ProductSN}")
            return jsonify(result)

        # 2. 如果没找到，循环查询 [SCPlan] 表中的记录
        query_scplan = f"""
            SELECT * FROM [{Table}].[dbo].[SCPlan]
            WHERE [WorkOrderNo] = ?
        """
        cursor.execute(query_scplan, work_order_no)
        rows_scplan = cursor.fetchall()

        for row_scplan in rows_scplan:
            # 3. 检查该记录是否已经存在于 [CtrlxIO_Production_New] 表中
            query_check_production = f"""
                SELECT 1 FROM [{Table}].[dbo].[CtrlxIO_Production]
                WHERE [WorkOrderNo] = ? AND [ProductSN] = ?
            """
            cursor.execute(query_check_production, work_order_no, row_scplan.ProductSN)
            row_production_check = cursor.fetchone()

            if not row_production_check:
                # 4. 如果不存在，则插入到 [CtrlxIO_Production_New] 表中
                query_insert_production = f"""
                    INSERT INTO [{Table}].[dbo].[CtrlxIO_Production]
                    ([WorkOrderNo], [ProductSN], [ProductWeek], [ProductLine], [ProductModel], [ProductNumber], [ProductItem], [tpCode], [BarCode], [ProductPlanLine], [PlanDate],[TestValue1],[TestValue2],[MSN],[PSN],[GXzt])
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,?,?,?,?,?)
                """
                cursor.execute(query_insert_production, 
                            row_scplan.WorkOrderNo,
                            row_scplan.ProductSN,
                            convert_to_week_format(row_scplan.PlanDate),
                            row_scplan.ProductLine, 
                            row_scplan.ProductModel,
                            row_scplan.ProductNumber, 
                            row_scplan.ProductItem, 
                            row_scplan.tpCode, 
                            row_scplan.BarCode, 
                            row_scplan.ProductPlanLine, 
                            row_scplan.PlanDate,
                            row_scplan.TestValue1,
                            row_scplan.TestValue2,
                            row_scplan.MSN,
                            row_scplan.PSN,
                            row_scplan.GXzt)
                conn.commit()

                # 返回插入的记录
                result = {
                    'WorkOrderNo': row_scplan.WorkOrderNo,
                    'ProductSN': row_scplan.ProductSN,
                    'ProductLine': row_scplan.ProductLine,
                    'ProductWeek': convert_to_week_format(row_scplan.PlanDate),
                    'ProductModel': row_scplan.ProductModel,
                    'ProductNumber': row_scplan.ProductNumber,
                    'ProductItem': row_scplan.ProductItem,
                    'tpCode': row_scplan.tpCode,
                    'BarCode': row_scplan.BarCode,
                    'ProductPlanLine': row_scplan.ProductPlanLine,
                    'PlanDate': row_scplan.PlanDate,
                    'TestValue1':row_scplan.TestValue1,
                    'TestValue2':row_scplan.TestValue2,
                    'MSN':row_scplan.MSN,
                    'PSN':row_scplan.PSN,
                    'GXzt':row_scplan.GXzt,
                    'error':''
                }
                cursor.close()
                conn.close()
                logging.info(f"message': 'get sn {row_scplan.ProductSN}")
                return jsonify(result)

        # 如果在 [SCPlan] 表中没有找到可插入的记录
        cursor.close()
        conn.close()
        logging.error(f"'error': 'No matching WorkOrderNo found in SCPlan or already exists in CtrlxIO_Production_New'")
        return jsonify({'error': 'No matching WorkOrderNo found in SCPlan or already exists in CtrlxIO_Production_New'}), 404
    except Exception as e:
        logging.error(f"Failed to get_sn: {str(e)}")
        return jsonify({'error': 'Failed to get_sn '}), 404

# Laserdone 功能：更新 ProductSN 对应的条目
@app.route('/laserdone', methods=['POST'])
def laserdone():
    # 从请求中获取 SN 参数
    try:
        product_sn = request.args.get('SN')
        
        # 检查是否提供了 SN 参数
        if not product_sn:
            logging.error(f"'error': 'No ProductSN provided'")
            return jsonify({'error': 'No ProductSN provided'}), 400

        conn = connect_to_db()
        cursor = conn.cursor()

        # 查询是否存在 ProductSN=X 的记录
        query_check_sn = f"""
            SELECT * FROM [{Table}].[dbo].[CtrlxIO_Production]
            WHERE [ProductSN] = ?
        """
        cursor.execute(query_check_sn, product_sn)
        row = cursor.fetchone()
        
        if row:
            # 更新 LaserStatus 为 'finished' 并写入当前时间到 TestValue10
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            query_update = f"""
                UPDATE [{Table}].[dbo].[CtrlxIO_Production]
                SET [LaserStatus] = 'finished', 
                    [TestValue10] = ?
                WHERE [ProductSN] = ?
            """
            cursor.execute(query_update, current_time, product_sn)
            conn.commit()

            result = {
                'ProductSN': product_sn,
                'LaserStatus': 'finished',
                'TestValue10': current_time,
                'error':''
            }

            cursor.close()
            conn.close()
            logging.info(f"'message': 'laserdone of {product_sn}'")
            return jsonify(result)
        else:
            cursor.close()
            conn.close()
            logging.error(f"'error': 'ProductSN not found'")
            return jsonify({'error': 'ProductSN not found'}), 404
    except Exception as e:
        logging.error(f"Failed to laserdone: {str(e)}")
        return jsonify({'error': 'ProductSN not found'}), 404
    
# Laserdone 功能：更新 ProductSN 对应的条目
@app.route('/assmbdone', methods=['POST'])
def assmbdone():
    try:
        # 从请求中获取 tpCode 和 BarCode 参数
        tp_code = request.args.get('tpCode')
        bar_code = request.args.get('BarCode')
        
        # 检查参数是否存在
        if not tp_code or not bar_code:
            logging.error(f"'error': 'tpCode and BarCode are required'")
            return jsonify({'error': 'tpCode and BarCode are required'}), 400

        conn = connect_to_db()
        cursor = conn.cursor()

        # 1. 查询并更新 tpCode=X 对应的记录，将 BarCode 设置为 Y，LaserStatus 设置为 'finished'
        query_update = f"""
            UPDATE [{Table}].[dbo].[CtrlxIO_Production]
            SET [BarCode] = ?, [AssbStatus] = 'finished', [TestValue11] = ?
            WHERE [tpCode] = ?
        """
        
        # 获取当前时间
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 执行更新操作
        cursor.execute(query_update, bar_code, current_time, tp_code)
        conn.commit()

        if cursor.rowcount == 0:
            # 如果没有找到任何记录进行更新，返回错误信息
            cursor.close()
            conn.close()
            logging.error(f"'error': 'No matching record found for the provided tpCode'")
            return jsonify({'error': 'No matching record found for the provided tpCode'}), 404

        # 查询更新后的记录并返回
        query_select = f"""
            SELECT * FROM [{Table}].[dbo].[CtrlxIO_Production]
            WHERE [tpCode] = ?
        """
        cursor.execute(query_select, tp_code)
        row = cursor.fetchone()

        if row:
            # 将结果转换为字典
            result = {
                'tpCode': row.tpCode,
                'BarCode': row.BarCode,
                'AssbStatus': row.LaserStatus,
                'TestValue11': row.TestValue10,
                'error':''
            }
            cursor.close()
            conn.close()
            logging.info(f"'message': 'Assbdone of {row.tpCode}+{row.BarCode}'")
            return jsonify(result)
        else:
            cursor.close()
            conn.close()
            logging.error(f"'error': 'Record not found after update'")
            return jsonify({'error': 'Record not found after update'}), 404
    except Exception as e:
        logging.error(f"Failed to assmbdone: {str(e)}")
        return jsonify({'error': 'Failed to assmbdone'})


@app.route('/submit_test', methods=['POST'])
def submit_test():
    try:
        # 1. 读取传来的 JSON 数据
        data = request.json
        
        # 2. 生成 GUID
        new_guid = str(uuid.uuid4())
        
        # 3. 解析 TpCode
        tp_code = data.get('TpCode', '')
        SN=tp_code[17:]
        # 4. 解析 result
        result = data.get('result', '')
        
        # 5. 读取当前系统时间
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 6. 获取 result 之后的所有字段并整合为 measurements
        measurements = []
        start_processing = False
        
        for key, value in data.items():
            if start_processing:
                # 从 result 项目之后开始处理每个字段
                measurement = {
                    "ItemName": key,
                    "timestamp": "",  # 如有需要可填充
                    "result": "",     # 如有需要可填充
                    "lowerLimit": "", # 如有需要可填充
                    "upperLimit": "", # 如有需要可填充
                    "value": str(value),
                    "unit": ""        # 如有需要可填充
                }
                measurements.append(measurement)
            
            # 当遇到 result 字段时，标记为开始处理之后的字段
            if key == 'result':
                start_processing = True
        
        # 7. 构建整合后的 JSON 数据 ,注意改CXL-3
        integrated_json = {
            "stationID": "CXL-3",
            "timestamp": current_time,
            "measurements": measurements
        }
        measurement_json=json.dumps(integrated_json)
        # 8. 插入到 CtrlX_IO_TestData 表
            # 连接数据库并插入数据到 [CtrlX_IO_TestData]
        
        conn = connect_to_db()
        cursor = conn.cursor()

        query_insert = f"""
            INSERT INTO [{Table}].[dbo].[CtrlX_IO_TestData]
            ([GUID], [SerialNumber], [TimeStamp], [Result], [TestRecord], [FlowTag])
            VALUES (?, ?, ?, ?, ?, 1)
        """
        cursor.execute(query_insert, new_guid, tp_code, current_time, result, measurement_json)
        

        # 如果 result 是 "PASS"，更新 [CtrlxIO_Production_New] 中 tpCode 对应的记录
        if result == "PASS":
            query_update = f"""
                UPDATE [{Table}].[dbo].[CtrlxIO_Production]
                SET [TestStatus] = ?, [TestValue12] = ?
                WHERE [ProductSN] = ?
            """
            cursor.execute(query_update, 'finished', current_time, SN)
        conn.commit()
        cursor.close()
        conn.close()
        
        logging.info(f"'message': 'Test data submitted successfully', 'GUID': {new_guid},'error':''")
        returnjson={'message':'Test data submitted successfully','error':''}
        return jsonify(returnjson)
    
    except Exception as e:
        logging.error(f"'error': 'Fail to Test data submitted', 'GUID': {new_guid}")
        return jsonify({'error': str(e)}), 500

@app.route('/repair', methods=['GET'])
def repair_record():
    try:
        # 从请求中获取 ProductSN 参数
        product_sn = request.args.get('SN')

        # 检查是否提供了 ProductSN 参数
        if not product_sn:
            logging.error(f"'error': 'No ProductSN provided'")
            return jsonify({'error': 'No ProductSN provided'}), 400

        # 连接到数据库
        conn = connect_to_db()
        cursor = conn.cursor()

        # 删除 [CtrlxIO_Production_New] 表中 [ProductSN] 对应的记录
        query_delete = f"""
            DELETE FROM [{Table}].[dbo].[CtrlxIO_Production]
            WHERE [ProductSN] = ?
        """
        cursor.execute(query_delete, product_sn)
        affected_rows = cursor.rowcount
        conn.commit()

        cursor.close()
        conn.close()

        # 如果没有删除任何记录，返回错误信息
        if affected_rows == 0:
            logging.error(f"'error': f'No record found with ProductSN: {product_sn}'")
            return jsonify({'error': f'No record found with ProductSN: {product_sn}'}), 404
        logging.info(f"'message': f'Record with ProductSN: {product_sn} deleted successfully'")
        return jsonify({f"'message': Record with ProductSN: {product_sn} deleted successfully，'error':''"}), 200
    except Exception as e:
        logging.error(f"'error': 'Fail to Remove SN', 'SN': {product_sn}")
        return jsonify({'error': str(e)}), 500

@app.route('/Test_index', methods=['GET'])
def Test_index():
    try:
        # 从请求中获取 ProductSN 参数
        product_sn = request.args.get('SN')
        EN9 = request.args.get('EN9')
        conn = connect_to_db()
        cursor = conn.cursor()
        if not product_sn:
            cursor.close()
            conn.close()
            logging.error(f"'error': 'No ProductSN provided'")
            return jsonify({'error': 'No ProductSN provided'}), 400  
        if not EN9:
            cursor.close()
            conn.close()
            logging.error(f"'error': 'No EN9 provided'")
            return jsonify({'error': 'No EN9 provided'}), 400
        if  EN9=='1':
            # 查询测试结果
            query_new = f"""
                SELECT [TestStatus],[TestValue7] FROM [{Table}].[dbo].[CtrlxIO_Production]
                WHERE [ProductSN] = ?
            """
            cursor.execute(query_new, product_sn)
            row_new = cursor.fetchone()
            if row_new:
            # 如果找到了符合条件的记录，返回该记录
                if row_new.TestStatus=='finished' and row_new.TestValue7=='finished':
                    result = {
                        'TestResult': 'PASS',
                        'error':''
                    }
                else:
                    result = {
                        'TestResult': 'FAIL',
                        'error':''
                    }
                cursor.close()
                conn.close()
                logging.info(f"message': 'get testresult sn {product_sn},'error':''")
                return jsonify(result)  
            logging.info(f"message': ' testresult: no such sn {product_sn},'error':'no such sn'")
            return jsonify(result)
        if  EN9=='0':
            # 查询测试结果
            query_new = f"""
                SELECT [TestStatus] FROM [{Table}].[dbo].[CtrlxIO_Production]
                WHERE [ProductSN] = ?
            """
            cursor.execute(query_new, product_sn)
            row_new = cursor.fetchone()
            if row_new:
            # 如果找到了符合条件的记录，返回该记录
                if row_new.TestStatus=='finished' :
                    result = {
                        'TestResult': 'PASS',
                        'error':''
                    }
                else:
                    result = {
                        'TestResult': 'FAIL',
                        'error':''
                    }
                cursor.close()
                conn.close()
                logging.info(f"message': 'get testresult sn {product_sn},'error':''")
                return jsonify(result)  
        if  EN9=='2':
            # 查询测试结果
            query_new = f"""
                SELECT [TestValue9] FROM [{Table}].[dbo].[CtrlxIO_Production]
                WHERE [ProductSN] = ?
            """
            cursor.execute(query_new, product_sn)
            row_new = cursor.fetchone()
            if row_new:
            # 如果找到了符合条件的记录，返回该记录
                if row_new.TestValue9=='finished' :
                    result = {
                        'TestResult': 'PASS',
                        'error':''
                    }
                else:
                    result = {
                        'TestResult': 'FAIL',
                        'error':''
                    }
                cursor.close()
                conn.close()
                logging.info(f"message': 'get testresult sn {product_sn},'error':''")
                return jsonify(result)  
            logging.info(f"message': ' testresult: no such sn {product_sn},'error':'no such sn'")
            return jsonify(result)
        if  EN9=='3':
            # 查询测试结果
            query_new = f"""
                SELECT [TestValue7],[TestValue9] FROM [{Table}].[dbo].[CtrlxIO_Production]
                WHERE [ProductSN] = ?
            """
            cursor.execute(query_new, product_sn)
            row_new = cursor.fetchone()
            if row_new:
            # 如果找到了符合条件的记录，返回该记录
                if row_new.TestValue9=='finished' and row_new.TestValue7=='finished' :
                    result = {
                        'TestResult': 'PASS',
                        'error':''
                    }
                else:
                    result = {
                        'TestResult': 'FAIL',
                        'error':''
                    }
                cursor.close()
                conn.close()
                logging.info(f"message': 'get testresult sn {product_sn},'error':''")
                return jsonify(result)  
            logging.info(f"message': ' testresult: no such sn {product_sn},'error':'no such sn'")
            return jsonify(result)
        logging.info(f"message': ' testresult: wrongin {product_sn},'error':'no such sn'")
        return jsonify({'message': f'testresult: wrongin:{product_sn}','error':'no such sn'})
    except Exception as e:
        logging.error(f"'error': 'Fail to Test_index SN', 'SN': {product_sn}")
        return jsonify({'error': str(e)}), 500


@app.route('/assmindex', methods=['GET'])
def Test_assmindex():
    try:
        # 从请求中获取 ProductSN 参数
        Tcode = request.args.get('TpCode')
        conn = connect_to_db()
        cursor = conn.cursor()
        if not Tcode:
            cursor.close()
            conn.close()
            logging.error(f"'error': 'No Tcode provided'")
            return jsonify({'error': 'No Tcode provided'}), 400 
       
        query_new = f"""
            SELECT [TestValue7],[TestValue8] FROM [{Table}].[dbo].[CtrlxIO_Production]
            WHERE tpCode = ?
        """
        cursor.execute(query_new, Tcode)
        row_new = cursor.fetchone()
        if row_new:
        # 如果找到了符合条件的记录，返回该记录          
            result = {
                'TestResult7': row_new.TestValue7,
                'TestResult8': row_new.TestValue8,
                'error':''
            }
            cursor.close()
            conn.close()
            logging.info(f"message': 'get testresult sn {Tcode},'error':''")
            return jsonify(result)  
        logging.info(f"message': ' testresult: no such sn {Tcode},'error':'no such sn'")
        return jsonify(result)
    except Exception as e:
        logging.error(f"'error': 'Fail to Test_index SN', 'SN': {Tcode}")
        return jsonify({'error': str(e)}), 500
@app.route('/')
def home():
    return render_template('home.html')



@app.route('/query')
def query():
    return render_template('query.html')

@app.route('/index', methods=['GET'])
def index():
    part_number = request.args.get('part_number')
    serial_number = request.args.get('serial_number')
    production_number = request.args.get('production_number')
    timestamp = request.args.get('timestamp')

    # 获取激光状态、组装状态、测试状态的筛选条件
    laser_status = request.args.get('laser_status')
    assb_status = request.args.get('assb_status')
    test_status = request.args.get('test_status')

    query_conditions = []
    parameters = []

    # 根据输入的 SN号、MNR号、生产编号、时间 进行筛选
    if part_number:
        query_conditions.append("ProductSN=?")
        parameters.append(part_number)
    if serial_number:
        query_conditions.append("ProductNumber=?")
        parameters.append(serial_number)
    if production_number:
        query_conditions.append("WorkOrderNo=?")
        parameters.append(production_number)
    if timestamp:
        query_conditions.append("PlanDate=?")
        datemode=config['Transfer']['datemode']

        date_obj = datetime.strptime(timestamp, "%Y-%m-%d")
        formatted_date = date_obj.strftime(datemode)
        parameters.append(formatted_date)
        

    # 激光状态筛选条件，若输入为 'none' 则查询为空值，否则查询具体值
    if laser_status == 'none':
        query_conditions.append("LaserStatus IS NULL")
    elif laser_status:
        query_conditions.append("LaserStatus=?")
        parameters.append(laser_status)

    # 组装状态筛选条件，若输入为 'none' 则查询为空值，否则查询具体值
    if assb_status == 'none':
        query_conditions.append("AssbStatus IS NULL")
    elif assb_status:
        query_conditions.append("AssbStatus=?")
        parameters.append(assb_status)

    # 测试状态筛选条件，若输入为 'none' 则查询为空值，否则查询具体值
    if test_status == 'none':
        query_conditions.append("TestStatus IS NULL")
    elif test_status:
        query_conditions.append("TestStatus=?")
        parameters.append(test_status)

    results = []
    if query_conditions:
        query = f"""
        SELECT ProductSN, ProductWeek, ProductNumber, PlanDate, WorkOrderNo, LaserStatus, AssbStatus, TestStatus
        FROM [{Table}].[dbo].[CtrlxIO_Production]
        WHERE """ + " AND ".join(query_conditions)

        connection = connect_to_db()
        cursor = connection.cursor()
        cursor.execute(query, parameters)
        results = cursor.fetchall()
        connection.close()

    # 传递结果数量
    result_count = len(results)

    return render_template('index.html', results=results, result_count=result_count)

@app.route('/detail/<sn>', methods=['GET', 'POST'])
def detail(sn):
    connection = connect_to_db()
    cursor = connection.cursor()

    if request.method == 'POST':
        # 处理表单提交以更新记录
        new_test_value8 = request.form['TestValue8']
        new_test_value9 = request.form['TestValue9']
        new_test_value10 = request.form['TestValue10']
        new_test_value11 = request.form['TestValue11']
        new_test_value12 = request.form['TestValue12']
        new_laser_status = request.form['LaserStatus']
        new_assb_status = request.form['AssbStatus']
        new_test_status = request.form['TestStatus']
        new_Barcode     = request.form['BarCode']
        update_query = f"""
        UPDATE [{Table}].[dbo].[CtrlxIO_Production]
        SET TestValue8 = ?, TestValue9 = ?, TestValue10 = ?, TestValue11 = ?, TestValue12 = ?, 
            LaserStatus = ?, AssbStatus = ?, TestStatus = ?,BarCode=?
        WHERE ProductSN = ?
        """
        cursor.execute(update_query, (new_test_value8, new_test_value9, new_test_value10, new_test_value11, 
                                      new_test_value12, new_laser_status, new_assb_status, new_test_status,new_Barcode, sn))
        connection.commit()

    # 获取详细记录
    detail_query = f"""
    SELECT WorkOrderNo, ProductSN, ProductWeek, ProductLine, ProductModel, ProductNumber, ProductItem, 
           tpCode, BarCode, ProductPlanLine, PlanDate, LaserStatus, AssbStatus, TestStatus, 
           TestValue8, TestValue9, TestValue10, TestValue11, TestValue12
    FROM [{Table}].[dbo].[CtrlxIO_Production]
    WHERE ProductSN = ?
    """
    cursor.execute(detail_query, sn)
    detail = cursor.fetchone()

    connection.close()

    return render_template('detail.html', detail=detail)

@app.route('/export', methods=['POST'])
def export():
    # 从 POST 请求中获取查询参数
    part_number = request.form.get('part_number')
    serial_number = request.form.get('serial_number')
    production_number = request.form.get('production_number')
    timestamp = request.form.get('timestamp')
    laser_status = request.form.get('laser_status')
    assb_status = request.form.get('assb_status')
    test_status = request.form.get('test_status')

    query_conditions = []
    parameters = []

    # 根据输入的条件设置查询
    if part_number:
        query_conditions.append("ProductSN=?")
        parameters.append(part_number)
    if serial_number:
        query_conditions.append("ProductNumber=?")
        parameters.append(serial_number)
    if production_number:
        query_conditions.append("WorkOrderNo=?")
        parameters.append(production_number)
    if timestamp:
        query_conditions.append("PlanDate=?")
        parameters.append(timestamp)

    if laser_status == 'none':
        query_conditions.append("LaserStatus IS NULL")
    elif laser_status:
        query_conditions.append("LaserStatus=?")
        parameters.append(laser_status)

    if assb_status == 'none':
        query_conditions.append("AssbStatus IS NULL")
    elif assb_status:
        query_conditions.append("AssbStatus=?")
        parameters.append(assb_status)

    if test_status == 'none':
        query_conditions.append("TestStatus IS NULL")
    elif test_status:
        query_conditions.append("TestStatus=?")
        parameters.append(test_status)

    query = f"""
    SELECT WorkOrderNo, ProductSN, ProductWeek, ProductLine, ProductModel, ProductNumber, ProductItem,
           tpCode, BarCode, ProductPlanLine, PlanDate,TestValue1, TestValue2, LaserStatus, AssbStatus, TestStatus,
           TestValue8, TestValue9, TestValue10, TestValue11, TestValue12
    FROM [{Table}].[dbo].[CtrlxIO_Production]
    WHERE """ + " AND ".join(query_conditions)

    # 获取数据库连接并执行查询
    connection = connect_to_db()
    cursor = connection.cursor()
    cursor.execute(query, parameters)
    rows = cursor.fetchall()
    connection.close()

    # 创建 CSV 文件
    csv_file = StringIO()
    csv_writer = csv.writer(csv_file)
    # 添加 CSV 文件头
    csv_writer.writerow([
        "WorkOrderNo", "ProductSN", "ProductWeek", "ProductLine", "ProductModel", "ProductNumber",
        "ProductItem", "tpCode", "BarCode", "ProductPlanLine", "PlanDate", "TestValue1", "TestValue2","LaserStatus",
        "AssbStatus", "TestStatus", "TestValue8", "TestValue9", "TestValue10", "TestValue11", "TestValue12"
    ])
    # 写入每一行数据
    for row in rows:
        csv_writer.writerow(row)

    # 准备文件响应并返回
    response = make_response(csv_file.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=export.csv"
    response.headers["Content-type"] = "text/csv"
    return response

@app.route('/delete_by_sn', methods=['DELETE'])
def delete_by_sn():
    product_sn = request.args.get('ProductSN')
    if not product_sn:
        return jsonify({"success": False, "error": "缺少SN号参数"}), 400
    
    try:
        connection = connect_to_db()
        cursor = connection.cursor()
        delete_query = f"DELETE FROM [{Table}].[dbo].[CtrlxIO_Production] WHERE ProductSN = ?"
        cursor.execute(delete_query, (product_sn,))
        connection.commit()
        
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        connection.close()


@app.route('/search', methods=['POST'])
def search():
    serial_number = request.form.get('serialNumber')
    result_filter = request.form.get('result')
    start_date = request.form.get('startDate')
    end_date = request.form.get('endDate')

    # 排除 TestRecord 列
    query = f"SELECT GUID, SerialNumber, TimeStamp, Result, FlowTag FROM [{Table}].[dbo].[CtrlX_IO_TestData] WHERE 1=1"
    params = []

    if serial_number:
        query += " AND SerialNumber LIKE ?"
        params.append(f"%{serial_number}%")

    if result_filter:
        query += " AND Result = ?"
        params.append(result_filter)

    if start_date:
        query += " AND TimeStamp >= ?"
        params.append(start_date)

    if end_date:
        query += " AND TimeStamp <= ?"
        params.append(end_date)

    connection = connect_to_db()
    cursor = connection.cursor()

    cursor.execute(query, params)
    records = cursor.fetchall()
    connection.close()

    # 转换记录为字典格式
    columns = [column[0] for column in cursor.description]
    results = [dict(zip(columns, row)) for row in records]

    return jsonify(results)


@app.route('/record/<guid>')
def show_record(guid):
    connection = connect_to_db()
    cursor = connection.cursor()

    # 查询 GUID 对应的记录
    cursor.execute(f"SELECT TestRecord FROM [{Table}].[dbo].[CtrlX_IO_TestData] WHERE GUID = ?", (guid,))
    record = cursor.fetchone()

    connection.close()

    if record:
        test_record = json.loads(record[0])  # 解析 JSON 字符串
        return render_template('record.html', test_record=test_record)
    else:
        return "Record not found", 404


@app.route('/manage_files', methods=['GET', 'POST'])
def manage_files():
    # 扫描要管理的文件夹
    process_files = os.listdir(config['paths']['file_process'])  # 扫描工艺文件夹
    other_files = os.listdir(config['paths']['file_product'])  # 扫描其他文件夹

    if request.method == 'POST':
        # 上传工艺文件
        if 'process_file' in request.files:
            file = request.files['process_file']
            if file.filename != '':
                file.save(os.path.join(config['paths']['file_process'], file.filename))
                flash('工艺文件上传成功！')
                return redirect(url_for('manage_files'))  # 上传后刷新页面

        # 删除文件
        if 'delete_file' in request.form:
            file_to_delete = request.form['delete_file']
            file_path_pd = os.path.join(config['paths']['file_process'], file_to_delete)
            file_path_of = os.path.join(config['paths']['file_product'], file_to_delete)

            # 尝试删除文件
            if os.path.exists(file_path_pd):
                os.remove(file_path_pd)
                flash(f'{file_to_delete} 从工艺文件夹中删除成功！')
            elif os.path.exists(file_path_of):
                os.remove(file_path_of)
                flash(f'{file_to_delete} 从其他文件夹中删除成功！')
            else:
                flash('文件不存在！')

            return redirect(url_for('manage_files'))  # 删除后刷新页面

    return render_template('manage_files.html', process_files=process_files, other_files=other_files)

# 提供文件下载
@app.route('/download_file/<folder>/<filename>')
def download_file(folder, filename):
    if folder == 'process_files':
        folder_path = config['paths']['file_process']
    elif folder == 'other_files':
        folder_path = config['paths']['file_product']
    else:
        flash('无效文件夹！')
        return redirect(url_for('manage_files'))

    file_path = os.path.join(folder_path, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        flash('文件不存在！')
        return redirect(url_for('manage_files'))


#查询导出CSPlan
@app.route('/scplan')
def scplanquery():
    return render_template('CSPlanquery.html')

@app.route('/query_scplan', methods=['GET'])
def query_scplan():
    work_order_no = request.args.get('WorkOrderNo')
    start_date = request.args.get('StartDate')
    end_date = request.args.get('EndDate')
    connection = connect_to_db()
    query = f"""
        SELECT 
            WorkOrderNo, 
            COUNT(*) AS EntryCount, 
            MAX(ProductNumber) AS MNR,
            MAX(PlanDate) AS SchedstartCN        
        FROM [{Table}].[dbo].[SCPlan]
    """
    params = []
    if work_order_no:
        query += " WHERE WorkOrderNo = ? "#去掉CXL-3，AND [ProductPlanLine]='CXL-3'
        params.append(work_order_no)
    elif start_date and end_date:
        query += " WHERE  PlanDate BETWEEN ? AND ? "#去掉CXL-3，[ProductPlanLine]='CXL-3' AND
        params.extend([start_date, end_date])

    query += " GROUP BY WorkOrderNo"

    df = pd.read_sql(query, connection, params=params)
    result = df.to_dict(orient='records')

    return jsonify(result)

  
@app.route('/export_scplan_details', methods=['GET'])
def export_scplan_details():
    # 获取并解析 WorkOrderNo 参数，分割为列表
    work_order_nos = request.args.get('WorkOrderNo')
    if not work_order_nos:
        return "Missing WorkOrderNo parameter", 400
    
    work_order_nos = work_order_nos.split(',')

    # 建立数据库连接
    connection = connect_to_db()

    # 查询详细信息，使用 IN 子句
    query = f"""
        SELECT 
            [ProductSN], 
            [ProductLine], 
            [ProductModel], 
            [ProductNumber], 
            [ProductItem], 
            [tpCode], 
            [BarCode], 
            [ProductPlanLine], 
            [WorkOrderNo],
            [TestValue1], 
            [TestValue2],
            [PlanDate]
        FROM [{Table}].[dbo].[SCPlan]
        WHERE WorkOrderNo IN ({','.join(['?'] * len(work_order_nos))})
    """
    
    # 使用参数化查询
    df = pd.read_sql(query, connection, params=work_order_nos)

    # 重命名列名为新的导出表头
    df.rename(columns={
        'ProductSN': 'ProductSN',
        'ProductLine': 'ProductLine',
        'ProductModel': 'ProductModel',
        'ProductNumber': 'ProductNumber',
        'ProductItem': 'ProductItem',
        'tpCode': 'tpCode',
        'BarCode': 'BarCode',
        'ProductPlanLine': 'ProductPlanLine',
        'WorkOrderNo': 'WorkOrderNo',
        'TestValue1':'TestValue1',
        'TestValue2':'TestValue2',
        'PlanDate': 'PlanDate'
    }, inplace=True)

    # 将 DataFrame 转换为 CSV 文件并返回
    output = BytesIO()
    df.to_csv(output, index=False, encoding='utf-8-sig')
    output.seek(0)

    return send_file(
        output, 
        as_attachment=True, 
        download_name=f'SCPlan_export.csv', 
        mimetype='text/csv'
    )


# 导入数据到 SCPlan 表
@app.route('/import_scplan', methods=['POST'])
def import_scplan():
    if 'file' not in request.files:
        return jsonify(message="未找到文件"), 400
    
    file = request.files['file']
    data = pd.read_csv(file)

    # Connect to the database
    connection = connect_to_db()
    cursor = connection.cursor()

    for _, row in data.iterrows():
        # Convert NaN values to None for SQL insertion
        row = row.where(pd.notnull(row), None)

        # Check if record already exists
        check_query = f"""
            SELECT COUNT(*) FROM [{Table}].[dbo].[SCPlan]
            WHERE ProductSN = ?
        """
        cursor.execute(check_query, (row['ProductSN'],))
        exists = cursor.fetchone()[0] > 0

        if exists:
            return jsonify(message=f"订单号 {row['WorkOrderNo']} 中的数据已存在"), 400

        # Insert data into the database
        insert_query = f"""
            INSERT INTO [{Table}].[dbo].[SCPlan] 
            (ProductSN, ProductLine, ProductModel, ProductNumber, ProductItem, tpCode, BarCode, ProductPlanLine, WorkOrderNo, PlanDate, TestValue1, TestValue2, MSN, PSN, GXzt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(insert_query, (
            row['ProductSN'], row['ProductLine'], row['ProductModel'], row['ProductNumber'],
            row['ProductItem'], row['tpCode'], row['BarCode'], row['ProductPlanLine'],
            row['WorkOrderNo'], row['PlanDate'], row['TestValue1'], row['TestValue2'],
            row['MSN'], row['PSN'], row['GXzt']
        ))
    
    connection.commit()
    cursor.close()
    connection.close()
    return jsonify(message="数据导入成功")


# 删除选中的订单
@app.route('/delete_scplan', methods=['POST'])
def delete_scplan():
    data = request.get_json()
    work_order_nos = data.get('workOrderNos')
    if not work_order_nos:
        return jsonify(message="缺少订单号参数"), 400

    connection = connect_to_db()
    cursor = connection.cursor()
    
    # 使用 SQL DELETE 语句删除选中的订单号
    delete_query = f"""
        DELETE FROM [{Table}].[dbo].[SCPlan]
        WHERE WorkOrderNo IN ({','.join(['?'] * len(work_order_nos))})
    """
    cursor.execute(delete_query, work_order_nos)
    connection.commit()
    cursor.close()
    connection.close()

    return jsonify(message="选中的订单已删除")

#查询安规记录
@app.route('/Hipotquery')
def Hipotquery():
    return render_template('Hipotquery.html')

@app.route('/Hipotsearch', methods=['POST'])
def Hipotsearch():
    serial_number = request.form.get('serialNumber')
    result_filter = request.form.get('result')
    start_date = request.form.get('startDate')
    end_date = request.form.get('endDate')

    # 排除 TestRecord 列
    query = f"SELECT GUID, SerialNumber, TimeStamp, Result, FlowTag FROM [{Table}].[dbo].[CtrlX_IO_HI_POT_TestData] WHERE 1=1"
    params = []

    if serial_number:
        query += " AND SerialNumber LIKE ?"
        params.append(f"%{serial_number}%")

    if result_filter:
        query += " AND Result = ?"
        params.append(result_filter)

    if start_date:
        query += " AND TimeStamp >= ?"
        params.append(start_date)

    if end_date:
        query += " AND TimeStamp <= ?"
        params.append(end_date)

    connection = connect_to_db()
    cursor = connection.cursor()

    cursor.execute(query, params)
    records = cursor.fetchall()
    connection.close()

    # 转换记录为字典格式
    columns = [column[0] for column in cursor.description]
    results = [dict(zip(columns, row)) for row in records]

    return jsonify(results)

@app.route('/Hipotrecord/<guid>')
def show_Hipotrecord(guid):
    connection = connect_to_db()
    cursor = connection.cursor()

    # 查询 GUID 对应的记录
    cursor.execute(f"SELECT TestRecord FROM [{Table}].[dbo].[CtrlX_IO_HI_POT_TestData] WHERE GUID = ?", (guid,))
    record = cursor.fetchone()

    connection.close()

    if record:
        test_record = json.loads(record[0])  # 解析 JSON 字符串
        return render_template('Hipotrecord.html', test_record=test_record)
    else:
        return "Record not found", 404



if __name__ == '__main__':
    host = config['server']['host']
    port = config['server']['port']
    app.run(host=host, port=port,debug=True)

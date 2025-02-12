logging.basicConfig(filename='server.log', level=logging.INFO, 
                    format='%(asctime)s %(levelname)s: %(message)s')


pyinstaller --onefile --add-data "templates;templates" --add-data "static;static" run_with_waitress.py

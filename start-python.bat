@echo off

echo Activating Python virtual environment...
if not exist venv (
    echo Virtual environment not found. Creating it first...
    echo You can use the command: python -m venv venv
    python -m venv venv
    rem exit /b 1
)
echo Activating venv...
if exist venv\Scripts\activate (
    call venv\Scripts\activate
) else (
    echo Activation script not found. Please ensure the virtual environment is set up correctly.
    exit /b 1
)
echo Python virtual environment activated.
echo Installing required packages...
echo pip install pydub moviepy==1.0.3
echo pip freeze > requirements.txt
echo pip install -r requirements.txt
echo.
pip install pydub moviepy==1.0.3
echo.
echo Required packages installed.
echo You can now run your Python scripts with the activated environment.
echo To deactivate the environment, run: call venv\Scripts\deactivate.bat or stop-python.bat
echo.

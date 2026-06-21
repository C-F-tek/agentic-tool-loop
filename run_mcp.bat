@echo off
:: Forza l'attivazione del venv corretto mantenendo le ENV di VS Code
call "C:\Users\carmi\AI\venvs\labtools\Scripts\activate.bat"
:: Esegue Python dal venv passando il file di script ricevuto come argomento (%1)
"C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe" -u %1
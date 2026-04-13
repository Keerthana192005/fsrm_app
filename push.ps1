$git = "C:\2025.1\tps\win64\git-2.46.0\bin\git.exe"
Set-Location "c:\Users\KARTHIK T R\Downloads\farm_app (3)\farm_app"
& $git init
& $git config user.email "keerthana@example.com"
& $git config user.name "Keerthana192005"
& $git add .
& $git commit -m "Initial commit"
& $git branch -M main
& $git remote add origin https://github.com/Keerthana192005/farm_app.git
& $git push -u origin main

# Устанавливает локальный pre-push хук: запрет прямых пушей в main.
# Запуск: powershell -ExecutionPolicy Bypass -File scripts\install-hooks.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$hooks = Join-Path $root '.git\hooks'
if (-not (Test-Path $hooks)) {
    throw "Не найден .git/hooks — запустите из корня репозитория."
}

$hook = Join-Path $hooks 'pre-push'
$content = @'
#!/bin/sh
# No direct pushes to main: branches and pull requests only.
protected="refs/heads/main refs/heads/master"
while read local_ref local_sha remote_ref remote_sha; do
  for branch in $protected; do
    if [ "$remote_ref" = "$branch" ]; then
      echo ""
      echo "  Direct push to main is blocked."
      echo "  Use a branch and a pull request:"
      echo "    git checkout -b fix/short-name"
      echo "    git push -u origin fix/short-name"
      echo "    python scripts/open_pr.py"
      echo ""
      exit 1
    fi
  done
done
exit 0
'@
Set-Content -Path $hook -Value $content -Encoding ascii -NoNewline
Write-Host "Хук установлен: $hook"
Write-Host "Проверка: git push (в main) должен завершиться отказом."

@echo off
rem Kept only to reject previously distributed WXBridgeUI commands.
rem This wrapper never launches Python, upstream WeChat or any UI action.
echo {"error":"wxbridge_ui_disabled","message":"WXBridge is read-only; state-changing commands are disabled."} 1>&2
exit /b 4

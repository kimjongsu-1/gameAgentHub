[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$gh = 'C:\Program Files\GitHub CLI\gh.exe'

if (-not (Test-Path -LiteralPath $gh)) {
    Write-Error 'GitHub CLI was not found.'
    exit 1
}

Write-Host 'GitHub secure token login' -ForegroundColor Cyan
Write-Host 'A masked paste-enabled input window will open.'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = 'GitHub secure token login'
$form.ClientSize = New-Object System.Drawing.Size(520, 175)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$label = New-Object System.Windows.Forms.Label
$label.Location = New-Object System.Drawing.Point(20, 18)
$label.Size = New-Object System.Drawing.Size(480, 42)
$label.Text = "Paste a newly issued GitHub token below.`r`nThe token is masked and is not written to a file by this script."
$form.Controls.Add($label)

$tokenBox = New-Object System.Windows.Forms.TextBox
$tokenBox.Location = New-Object System.Drawing.Point(20, 68)
$tokenBox.Size = New-Object System.Drawing.Size(480, 26)
$tokenBox.UseSystemPasswordChar = $true
$tokenBox.ShortcutsEnabled = $true
$form.Controls.Add($tokenBox)

$loginButton = New-Object System.Windows.Forms.Button
$loginButton.Location = New-Object System.Drawing.Point(324, 116)
$loginButton.Size = New-Object System.Drawing.Size(84, 32)
$loginButton.Text = 'Login'
$loginButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
$form.AcceptButton = $loginButton
$form.Controls.Add($loginButton)

$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Location = New-Object System.Drawing.Point(416, 116)
$cancelButton.Size = New-Object System.Drawing.Size(84, 32)
$cancelButton.Text = 'Cancel'
$cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.CancelButton = $cancelButton
$form.Controls.Add($cancelButton)

$form.Add_Shown({ $tokenBox.Focus() })
$dialogResult = $form.ShowDialog()
if ($dialogResult -ne [System.Windows.Forms.DialogResult]::OK -or [string]::IsNullOrWhiteSpace($tokenBox.Text)) {
    $form.Dispose()
    Write-Host 'Login cancelled.' -ForegroundColor Yellow
    exit 1
}

$secureToken = ConvertTo-SecureString $tokenBox.Text -AsPlainText -Force
$tokenBox.Clear()
$form.Dispose()
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
$plainToken = $null
try {
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
    $plainToken | & $gh auth login --hostname github.com --git-protocol https --with-token
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub authentication failed with exit code $LASTEXITCODE."
    }
}
finally {
    if ($tokenPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    }
    $plainToken = $null
    $secureToken.Dispose()
    [GC]::Collect()
}

Write-Host ''
& $gh auth status
if ($LASTEXITCODE -eq 0) {
    Write-Host ''
    Write-Host 'GitHub CLI authentication succeeded. You can close this window.' -ForegroundColor Green
} else {
    Write-Error 'Authentication was not saved.'
    exit 1
}

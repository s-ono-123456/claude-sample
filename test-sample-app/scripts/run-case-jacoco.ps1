<#
.SYNOPSIS
  JUnitのテストケースを1件ずつ個別実行し、ケースごとに独立したJaCoCoカバレッジを取得する。

.DESCRIPTION
  Gradleで増分コンパイルしたクラスを使い、JUnit Platform Console Standalone でテストメソッドを
  1件ずつ実行する。各実行にJaCoCoエージェントを手動でアタッチし、ケースごとに別の .exec ファイルと
  HTML/XMLレポートを生成する。これにより「どのケースがどの行・分岐を通ったか」をケース単位で比較できる。

.PARAMETER TestClass
  対象のテストクラスの完全修飾名。

.PARAMETER Cases
  slug(出力ディレクトリ名) -> テストメソッド名 の順序付きハッシュテーブル。省略時はデフォルト5ケース。

.PARAMETER OutDir
  プロジェクトルートからの出力先相対ディレクトリ。
#>
param(
    [string]$TestClass = "com.example.testsampleapp.service.OrderCalculationServiceImplTest",
    $Cases,
    [string]$OutDir = "build/case-jacoco"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

if (-not $Cases) {
    $Cases = [ordered]@{
        "case1_order_not_found"    = "calculateOrderAmount_注文が存在しない場合は例外を投げる"
        "case2_customer_not_found" = "calculateOrderAmount_顧客が存在しない場合は例外を投げる"
        "case3_product_not_found"  = "calculateOrderAmount_商品が存在しない場合は例外を投げる"
        "case4_basic_case"         = "calculateOrderAmount_基本ケースで金額とポイントが正しく計算される"
        "case5_composite_case"     = "calculateOrderAmount_複合ケースでキャンペーンとクーポンと大量注文割引が反映される"
    }
}

function Extract-Between {
    param([string]$Text, [string]$StartMarker, [string]$EndMarker)
    $pattern = "$StartMarker\r?\n(.*?)\r?\n$EndMarker"
    $m = [regex]::Match($Text, $pattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if (-not $m.Success) {
        throw "マーカー $StartMarker/$EndMarker が見つかりません"
    }
    return $m.Groups[1].Value.Trim()
}

Write-Host "=== コンパイル(増分) ==="
& .\gradlew compileJava compileTestJava -q --console=plain

Write-Host "=== 依存解決(クラスパス / JUnit Console / JaCoCo agent・cli) ==="
$initScript = "scripts\resolve-jacoco-deps.init.gradle"
$resolveOutput = (& .\gradlew -I $initScript printTestClasspath resolveJunitConsole resolveJacocoAgent resolveJacocoCli -q --console=plain) -join "`n"

$testClasspath   = Extract-Between $resolveOutput "TESTCP_START" "TESTCP_END"
$junitConsoleJar = Extract-Between $resolveOutput "JUNITCONSOLE_START" "JUNITCONSOLE_END"
$jacocoAgentJar  = Extract-Between $resolveOutput "JACOCOAGENT_START" "JACOCOAGENT_END"
$jacocoCliJar    = Extract-Between $resolveOutput "JACOCOCLI_START" "JACOCOCLI_END"

$mainClasses   = Join-Path $root "build\classes\java\main"
$testClasses   = Join-Path $root "build\classes\java\test"
$mainResources = Join-Path $root "build\resources\main"
$srcMainJava   = Join-Path $root "src\main\java"
$fullClasspath = "$mainClasses;$testClasses;$mainResources;$junitConsoleJar;$testClasspath"

$outRoot = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $outRoot | Out-Null

$summary = @()

foreach ($slug in $Cases.Keys) {
    $methodName = $Cases[$slug]
    $caseDir = Join-Path $outRoot $slug
    New-Item -ItemType Directory -Force -Path $caseDir | Out-Null
    $execFile = Join-Path $caseDir "jacoco.exec"
    $htmlDir  = Join-Path $caseDir "report-html"
    $xmlFile  = Join-Path $caseDir "report.xml"

    Write-Host ""
    Write-Host "=== $slug : $methodName ==="

    & java "-javaagent:${jacocoAgentJar}=destfile=$execFile" -cp $fullClasspath `
        org.junit.platform.console.ConsoleLauncher --select-method "$TestClass#$methodName" --details=tree

    & java -cp $jacocoCliJar org.jacoco.cli.internal.Main report $execFile `
        --classfiles $mainClasses --sourcefiles $srcMainJava `
        --html $htmlDir --xml $xmlFile --name $slug

    [xml]$reportXml = Get-Content $xmlFile -Raw
    $targetClass = $reportXml.report.package.class | Where-Object {
        $_.name -eq "com/example/testsampleapp/service/OrderCalculationServiceImpl"
    }
    $methodNode = $targetClass.method | Where-Object { $_.name -eq "calculateOrderAmount" }
    $lineCounter = $methodNode.counter | Where-Object { $_.type -eq "LINE" }
    $branchCounter = $methodNode.counter | Where-Object { $_.type -eq "BRANCH" }

    $summary += [PSCustomObject]@{
        Case          = $slug
        LineCovered   = [int]$lineCounter.covered
        LineMissed    = [int]$lineCounter.missed
        BranchCovered = if ($branchCounter) { [int]$branchCounter.covered } else { 0 }
        BranchMissed  = if ($branchCounter) { [int]$branchCounter.missed } else { 0 }
    }
}

Write-Host ""
Write-Host "=== ケース別カバレッジサマリ（calculateOrderAmount） ==="
$summary | Format-Table -AutoSize

Write-Host ""
Write-Host "各ケースのHTMLレポート: $outRoot\<case>\report-html\index.html"

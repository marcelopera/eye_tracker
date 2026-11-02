param(
    [string]$Jdk = 'C:\Program Files\Android\Android Studio\jbr',
    [string]$GradleCache = "$env:USERPROFILE\.gradle\caches\modules-2\files-2.1"
)
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$output = Join-Path $workspace 'apps/android/app/build/tmp/validacao-mvvm-enxuto'
$production = Join-Path $workspace 'apps/android/app/build/intermediates/built_in_kotlinc/debug/compileDebugKotlin/classes'
if (!(Test-Path -LiteralPath $production)) { throw 'Execute :app:testDebugUnitTest primeiro.' }
New-Item -ItemType Directory -Path $output -Force | Out-Null
function CachedJar([string]$artifact) {
    $jar = Get-ChildItem -LiteralPath (Join-Path $GradleCache $artifact) -Recurse -Filter '*.jar' |
        Where-Object { $_.Name -notmatch '-(sources|javadoc)\.jar$' } | Select-Object -First 1
    if (!$jar) { throw "JAR não encontrado: $artifact" }
    return $jar.FullName
}
$stdlib = CachedJar 'org.jetbrains.kotlin/kotlin-stdlib/2.2.10'
$core = CachedJar 'org.jetbrains.kotlinx/kotlinx-coroutines-core-jvm/1.11.0'
$test = CachedJar 'org.jetbrains.kotlinx/kotlinx-coroutines-test-jvm/1.11.0'
$annotations = CachedJar 'org.jetbrains/annotations/23.0.0'
$compiler = @(
    (CachedJar 'org.jetbrains.kotlin/kotlin-compiler-embeddable/2.2.10'),
    $stdlib,
    (CachedJar 'org.jetbrains.kotlin/kotlin-script-runtime/2.2.10'),
    (CachedJar 'org.jetbrains.kotlin/kotlin-reflect/2.2.10'),
    $core,
    $annotations
) -join [IO.Path]::PathSeparator
$classpath = @($stdlib, $core, $test, $annotations, $production) -join [IO.Path]::PathSeparator
$java = Join-Path $Jdk 'bin/java.exe'
& $java -cp $compiler org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -no-stdlib -no-reflect -jvm-target 11 -classpath $classpath -d $output (Join-Path $PSScriptRoot 'ReproduzirAchados.kt')
if ($LASTEXITCODE -ne 0) { throw 'Falha na compilação do diagnóstico.' }
& $java -cp ($output + [IO.Path]::PathSeparator + $classpath) validacao.mvvm.ReproduzirAchadosKt
if ($LASTEXITCODE -ne 0) { throw 'Resultado diferente dos achados registrados; reavaliar o diagnóstico.' }

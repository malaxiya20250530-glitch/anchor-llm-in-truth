#!/data/data/com.termux/files/usr/bin/bash
set -e

APP_DIR=$HOME/ling-hui/android_app/app
BUILD_DIR=$HOME/ling-hui/android_app/build/manual
ANDROID_JAR=$HOME/android-sdk/platforms/android-34/android.jar
GRADLE_CACHE=$HOME/.gradle/caches/modules-2/files-2.1
TMP=$HOME/tmp_aar

APPCOMPAT_AAR=$(find $GRADLE_CACHE -name "appcompat-1.6.1.aar" 2>/dev/null | head -1)
GSON_JAR=$(find $GRADLE_CACHE -name "gson-2.*.jar" 2>/dev/null | head -1)

echo "=== 清理 ==="
rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR/{gen,obj,dex,libs}

echo "=== 提取 AppCompat AAR ==="
rm -rf $TMP 2>/dev/null; mkdir -p $TMP
cd $TMP
unzip -qo "$APPCOMPAT_AAR"
cp classes.jar $BUILD_DIR/libs/appcompat.jar
find res -name "*.xml" -exec sed -i 's|xmlns:app="http://schemas.android.com/apk/res-auto"|xmlns:app="http://schemas.android.com/apk/res/android"|g' {} +
cd -

echo "=== 下载 OkHttp/Gson ==="
cd $TMP
[ ! -f okhttp-4.12.0.jar ] && curl -sL "https://repo1.maven.org/maven2/com/squareup/okhttp3/okhttp/4.12.0/okhttp-4.12.0.jar" -o okhttp-4.12.0.jar
[ ! -f okio-3.6.0.jar ] && curl -sL "https://repo1.maven.org/maven2/com/squareup/okio/okio/3.6.0/okio-3.6.0.jar" -o okio-3.6.0.jar
[ ! -f kotlin-stdlib-1.9.10.jar ] && curl -sL "https://repo1.maven.org/maven2/org/jetbrains/kotlin/kotlin-stdlib/1.9.10/kotlin-stdlib-1.9.10.jar" -o kotlin-stdlib-1.9.10.jar
cp okhttp-4.12.0.jar $BUILD_DIR/libs/okhttp.jar
cp okio-3.6.0.jar $BUILD_DIR/libs/okio.jar
cp kotlin-stdlib-1.9.10.jar $BUILD_DIR/libs/kotlin-stdlib.jar
cp "$GSON_JAR" $BUILD_DIR/libs/gson.jar
cd -

echo "=== 编译 AppCompat 资源 ==="
cd $TMP
aapt2 compile -v --dir res -o $BUILD_DIR/obj/appcompat.zip 2>&1 | tail -1
cd -

echo "=== 编译应用资源 ==="
cd $BUILD_DIR
aapt2 compile -v --dir $APP_DIR/src/main/res -o obj/app_res.zip 2>&1 | tail -1

echo "=== 链接资源 + R.java ==="
aapt2 link -v \
  -I "$ANDROID_JAR" \
  --manifest "$APP_DIR/src/main/AndroidManifest.xml" \
  --java gen \
  -o obj/resources.apk \
  obj/app_res.zip obj/appcompat.zip 2>&1 | grep -E 'error|Done' || true
[ -f obj/resources.apk ] && echo "✓ 资源链接成功" || { echo "✗ 资源链接失败"; exit 1; }

echo "=== 编译 Java ==="
CLASSPATH="$ANDROID_JAR:libs/appcompat.jar:libs/gson.jar:libs/okhttp.jar:libs/okio.jar:libs/kotlin-stdlib.jar"
find $APP_DIR/src/main/java -name "*.java" > obj/sources.txt
javac -d obj/classes -cp "$CLASSPATH" -source 1.8 -target 1.8 -bootclasspath "$ANDROID_JAR" @obj/sources.txt 2>&1 && echo "✓ Java编译成功" || { echo "✗ Java编译失败"; exit 1; }

echo "=== 生成 DEX ==="
D8=$HOME/android-sdk/build-tools/34.0.0/lib/d8.jar
for jar in libs/*.jar; do
  java -Xmx512M -jar "$D8" --lib "$ANDROID_JAR" --release --output dex "$jar" 2>&1
done
java -Xmx512M -jar "$D8" --lib "$ANDROID_JAR" --release --output dex obj/classes 2>&1 && echo "✓ DEX生成成功"

echo "=== 打包 APK ==="
cp obj/resources.apk obj/base.apk
cd dex && zip -q0 ../obj/base.apk classes*.dex && cd ..

echo "=== 签名 ==="
APKSIGNER=$HOME/android-sdk/build-tools/34.0.0/lib/apksigner.jar
KS=$HOME/.android/debug.keystore
if [ ! -f "$KS" ]; then
  keytool -genkey -v -keystore "$KS" -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 -storepass android -keypass android -dname "CN=Debug" 2>&1 | tail -1
fi
java -jar "$APKSIGNER" sign --ks "$KS" --ks-pass pass:android --ks-key-alias androiddebugkey --key-pass pass:android obj/base.apk 2>&1 && echo "✓ 签名成功"

cp obj/base.apk $HOME/ling-hui.apk
echo "✅ APK: $HOME/ling-hui.apk ($(du -h $HOME/ling-hui.apk | cut -f1))"

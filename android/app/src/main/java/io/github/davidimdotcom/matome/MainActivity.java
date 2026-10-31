package io.github.davidimdotcom.matome;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.core.content.FileProvider;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.Collections;

/**
 * 마토메 보드 안드로이드 앱. 공개 페이지(GitHub Pages)를 주소창 없이 전체 화면 WebView 로 연다.
 * 내용은 늘 사이트에서 오므로 보드가 바뀌어도 앱을 다시 깔 필요가 없다.
 * WebView 에 없는 것 두 가지만 채운다: 파일 내려받기(달력 .ics·그림 저장)와 공유(navigator.share) → 아래 SHIM 과 Bridge.
 */
public class MainActivity extends Activity {
    static final String HOST = "davidim-dotcom.github.io";
    static final String PATH = "/matome-board";
    static final String HOME = "https://" + HOST + PATH + "/";

    // 모든 프레임(게임 iframe 포함)에 문서 시작 때 넣는 스크립트:
    // ① a[download] 로 blob:/data: 를 받는 클릭을 가로채 MatomeApp.save 로 넘김(WebView 는 download 속성을 무시한다)
    // ② 페이지가 곧바로 revokeObjectURL 해도 읽을 수 있게 1분 늦춤
    // ③ navigator.share / canShare 를 안드로이드 공유 창으로
    static final String SHIM = "(function(){if(window.__matomeShim)return;window.__matomeShim=1;var A=window.MatomeApp;if(!A)return;"
            + "var rv=URL.revokeObjectURL;URL.revokeObjectURL=function(u){setTimeout(function(){rv.call(URL,u)},60000)};"
            + "function b64(bl){return new Promise(function(ok,no){var r=new FileReader();r.onload=function(){ok(String(r.result).split(',')[1]||'')};r.onerror=no;r.readAsDataURL(bl)})}"
            + "function save(a){var n=a.getAttribute('download')||'matome';fetch(a.href).then(function(r){return r.blob()}).then(function(bl){return b64(bl).then(function(d){A.save(n,bl.type||'',d)})}).catch(function(){})}"
            + "var oc=HTMLAnchorElement.prototype.click;HTMLAnchorElement.prototype.click=function(){if(this.hasAttribute('download')&&/^(blob|data):/.test(this.href)){save(this);return}return oc.apply(this,arguments)};"
            + "document.addEventListener('click',function(e){var a=e.target&&e.target.closest&&e.target.closest('a[download]');if(a&&/^(blob|data):/.test(a.href)){e.preventDefault();save(a)}},true);"
            + "navigator.share=function(d){d=d||{};var f=d.files&&d.files[0];if(f)return b64(f).then(function(x){A.shareFile(f.name||'matome.png',f.type||'',x,[d.text,d.url].filter(Boolean).join(' '))});A.share(d.title||'',d.text||'',d.url||'');return Promise.resolve()};"
            + "navigator.canShare=function(){return true};"
            + "})();";

    WebView web;
    boolean startScript;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        setContentView(web);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false); // 게임 소리
        s.setSupportMultipleWindows(false); // target=_blank 도 같은 화면으로 와서 아래에서 바깥 링크로 걸러진다
        s.setUserAgentString(s.getUserAgentString() + " MatomeApp/" + versionName());
        web.addJavascriptInterface(new Bridge(), "MatomeApp");
        startScript = WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT);
        if (startScript) WebViewCompat.addDocumentStartJavaScript(web, SHIM, Collections.singleton("https://" + HOST));
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if (inApp(u)) return false;
                openOutside(u);
                return true;
            }

            @Override
            public void onPageStarted(WebView v, String url, Bitmap icon) {
                if (!startScript) v.evaluateJavascript(SHIM, null); // 옛 WebView: 첫 프레임에만
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (r.isForMainFrame()) showOffline();
            }
        });
        if (state != null) web.restoreState(state);
        else web.loadUrl(startUrl(getIntent()));
    }

    String versionName() {
        try { return getPackageManager().getPackageInfo(getPackageName(), 0).versionName; } catch (Exception e) { return "1"; }
    }

    static boolean inApp(Uri u) {
        String sc = u.getScheme();
        if ("blob".equals(sc) || "data".equals(sc) || "about".equals(sc)) return true;
        String p = u.getPath() == null ? "" : u.getPath();
        return "https".equals(sc) && HOST.equals(u.getHost()) && p.startsWith(PATH);
    }

    String startUrl(Intent it) {
        Uri u = it == null ? null : it.getData();
        return u != null && inApp(u) ? u.toString() : HOME;
    }

    void openOutside(Uri u) {
        try {
            Intent it = "intent".equals(u.getScheme()) ? Intent.parseUri(u.toString(), Intent.URI_INTENT_SCHEME) : new Intent(Intent.ACTION_VIEW, u);
            it.addCategory(Intent.CATEGORY_BROWSABLE);
            it.setComponent(null);
            it.setSelector(null);
            startActivity(it);
        } catch (Exception e) {
            toast("열 수 있는 앱이 없어요");
        }
    }

    void showOffline() {
        String html = "<!doctype html><meta name=viewport content='width=device-width'><body style='margin:0;display:grid;place-items:center;height:100vh;"
                + "font-family:sans-serif;background:#13152A;color:#ECEDF6;text-align:center'><div><p style='font-size:18px;font-weight:700'>인터넷에 연결되지 않았어요</p>"
                + "<p style='color:#9A9EBB'>연결을 확인한 뒤 다시 시도해 주세요.</p><button onclick=\"location.href='" + HOME + "'\" style='margin-top:12px;padding:12px 22px;"
                + "border:0;border-radius:999px;background:#FF5C9A;color:#fff;font-size:16px;font-weight:700'>다시 시도</button></div>";
        web.loadDataWithBaseURL(HOME, html, "text/html", "utf-8", null);
    }

    @Override
    protected void onNewIntent(Intent it) {
        super.onNewIntent(it);
        if (it != null && it.getData() != null && inApp(it.getData())) web.loadUrl(it.getData().toString());
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onPause() { super.onPause(); web.onPause(); }

    @Override
    protected void onResume() { super.onResume(); web.onResume(); }

    void toast(String m) { runOnUiThread(() -> Toast.makeText(this, m, Toast.LENGTH_SHORT).show()); }

    static String safeName(String n) {
        n = n == null ? "" : n.replaceAll("[\\\\/:*?\"<>|]", "_").trim();
        return n.isEmpty() ? "matome" : n;
    }

    static String mimeOf(String name, String mime) {
        if (mime != null && !mime.isEmpty()) return mime;
        String n = name.toLowerCase();
        if (n.endsWith(".ics")) return "text/calendar";
        if (n.endsWith(".png")) return "image/png";
        if (n.endsWith(".jpg") || n.endsWith(".jpeg")) return "image/jpeg";
        if (n.endsWith(".wav")) return "audio/wav";
        return "application/octet-stream";
    }

    File cacheFile(String name, byte[] data) throws Exception {
        File dir = new File(getCacheDir(), "share");
        dir.mkdirs();
        File f = new File(dir, safeName(name));
        try (FileOutputStream o = new FileOutputStream(f)) { o.write(data); }
        return f;
    }

    Uri shareUri(File f) { return FileProvider.getUriForFile(this, getPackageName() + ".files", f); }

    /** 페이지 스크립트가 부르는 다리(window.MatomeApp). 보드 주소 밖으로는 나가지 않으므로 보드 페이지만 부른다. */
    class Bridge {
        @JavascriptInterface
        public void save(String name, String mime, String b64) {
            runOnUiThread(() -> {
                try {
                    String n = safeName(name), m = mimeOf(n, mime);
                    byte[] data = Base64.decode(b64, Base64.DEFAULT);
                    if (n.toLowerCase().endsWith(".ics")) { // 달력 파일은 달력 앱으로 바로 연다
                        Uri u = shareUri(cacheFile(n, data));
                        Intent v = new Intent(Intent.ACTION_VIEW).setDataAndType(u, "text/calendar").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        try { startActivity(Intent.createChooser(v, "달력에 추가")); }
                        catch (ActivityNotFoundException e) { sendFile(u, m, "", "달력 파일 보내기"); }
                        return;
                    }
                    if (Build.VERSION.SDK_INT >= 29) { // 그림은 사진첩(Pictures/Matome), 그 밖은 다운로드 폴더
                        boolean img = m.startsWith("image/");
                        ContentValues cv = new ContentValues();
                        cv.put(MediaStore.MediaColumns.DISPLAY_NAME, n);
                        cv.put(MediaStore.MediaColumns.MIME_TYPE, m);
                        cv.put(MediaStore.MediaColumns.RELATIVE_PATH, img ? Environment.DIRECTORY_PICTURES + "/Matome" : Environment.DIRECTORY_DOWNLOADS);
                        Uri col = img ? MediaStore.Images.Media.EXTERNAL_CONTENT_URI : MediaStore.Downloads.EXTERNAL_CONTENT_URI;
                        Uri u = getContentResolver().insert(col, cv);
                        if (u == null) throw new Exception("insert");
                        try (OutputStream o = getContentResolver().openOutputStream(u)) { o.write(data); }
                        toast(img ? "사진첩에 저장했어요" : "다운로드 폴더에 저장했어요");
                    } else { // 안드로이드 9 이하는 저장 권한 대신 공유 창으로
                        sendFile(shareUri(cacheFile(n, data)), m, "", "저장하거나 보내기");
                    }
                } catch (Exception e) {
                    toast("저장하지 못했어요");
                }
            });
        }

        @JavascriptInterface
        public void share(String title, String text, String url) {
            runOnUiThread(() -> {
                String body = text == null || text.isEmpty() ? url : url == null || url.isEmpty() || text.contains(url) ? text : text + "\n" + url;
                Intent it = new Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, body);
                if (title != null && !title.isEmpty()) it.putExtra(Intent.EXTRA_SUBJECT, title);
                try { startActivity(Intent.createChooser(it, "공유")); } catch (Exception e) { toast("공유할 앱이 없어요"); }
            });
        }

        @JavascriptInterface
        public void shareFile(String name, String mime, String b64, String text) {
            runOnUiThread(() -> {
                try {
                    String n = safeName(name);
                    sendFile(shareUri(cacheFile(n, Base64.decode(b64, Base64.DEFAULT))), mimeOf(n, mime), text, "공유");
                } catch (Exception e) {
                    toast("공유하지 못했어요");
                }
            });
        }
    }

    void sendFile(Uri u, String mime, String text, String title) {
        Intent it = new Intent(Intent.ACTION_SEND).setType(mime).putExtra(Intent.EXTRA_STREAM, u).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        if (text != null && !text.isEmpty()) it.putExtra(Intent.EXTRA_TEXT, text);
        try { startActivity(Intent.createChooser(it, title)); } catch (Exception e) { toast("보낼 앱이 없어요"); }
    }
}

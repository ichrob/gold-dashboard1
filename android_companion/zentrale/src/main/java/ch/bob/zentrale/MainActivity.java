package ch.bob.zentrale;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Color;
import android.net.http.SslError;
import android.webkit.*;
import android.widget.*;
import android.view.View;
import java.io.ByteArrayInputStream;

/** Separate signed launcher app; web UI updates use the existing Bob server. */
public final class MainActivity extends Activity {
    private WebView web;
    private TextView message;
    private String retryUrl = NavigationPolicy.HOME;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        WebView.setWebContentsDebuggingEnabled(false);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setBackgroundColor(Color.rgb(12,19,33));
        layout.setOnApplyWindowInsetsListener((view, insets) -> {
            view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        LinearLayout tools = new LinearLayout(this);
        Button home = new Button(this); home.setText("Zentrale");
        Button reload = new Button(this); reload.setText("Neu laden");
        tools.addView(home); tools.addView(reload); layout.addView(tools);
        message = new TextView(this); message.setTextColor(Color.WHITE);
        message.setPadding(16,8,16,8); message.setText("Bob Zentrale wird geladen …");
        layout.addView(message);
        web = new WebView(this);
        layout.addView(web, new LinearLayout.LayoutParams(-1,0,1));
        setContentView(layout);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSafeBrowsingEnabled(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (NavigationPolicy.internal(request.getUrl().toString())) return false;
                message.setText("Dieser Link gehört nicht zur Bob Zentrale und wurde nicht geöffnet.");
                message.setVisibility(View.VISIBLE); return true;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (NavigationPolicy.internal(request.getUrl().toString())) return null;
                return new WebResourceResponse("text/plain", "UTF-8", 403, "Blocked", null,
                    new ByteArrayInputStream(new byte[0]));
            }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                if (!NavigationPolicy.internal(url)) { view.stopLoading(); return; }
                retryUrl = url; message.setText("Wird geladen …"); message.setVisibility(View.VISIBLE);
            }
            @Override public void onPageFinished(WebView view, String url) {
                if ("Wird geladen …".contentEquals(message.getText())) message.setVisibility(View.GONE);
                CookieManager.getInstance().flush();
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    message.setText("Bob ist momentan nicht erreichbar. Internet prüfen und Neu laden antippen.");
                    message.setVisibility(View.VISIBLE);
                }
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame()) {
                    message.setText("Bob antwortet mit einem Fehler. Bitte später Neu laden antippen.");
                    message.setVisibility(View.VISIBLE);
                }
            }
            @Override public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel(); message.setText("Sichere Verbindung nicht bestätigt. Laden abgebrochen.");
                message.setVisibility(View.VISIBLE);
            }
        });
        home.setOnClickListener(v -> web.loadUrl(NavigationPolicy.HOME));
        reload.setOnClickListener(v -> web.loadUrl(NavigationPolicy.internal(retryUrl) ? retryUrl : NavigationPolicy.HOME));
        // Incoming intents cannot select URLs or pass credentials into this app.
        web.loadUrl(NavigationPolicy.HOME);
    }
    @Override public void onBackPressed() { if (web.canGoBack()) web.goBack(); else super.onBackPressed(); }
    @Override protected void onPause() { web.onPause(); CookieManager.getInstance().flush(); super.onPause(); }
    @Override protected void onResume() { super.onResume(); if (web != null) web.onResume(); }
    @Override protected void onDestroy() { web.stopLoading(); web.destroy(); super.onDestroy(); }
}

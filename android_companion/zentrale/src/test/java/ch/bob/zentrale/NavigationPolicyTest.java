package ch.bob.zentrale;
import org.junit.Test;
import static org.junit.Assert.*;
public class NavigationPolicyTest {
    @Test public void permitsBobLoginAndHub() {
        for (String url : new String[]{NavigationPolicy.HOME,"https://bob-private-scanner.onrender.com/login?view=zentrale","https://bob-private-scanner.onrender.com:443/api/operations-summary"}) assertTrue(url,NavigationPolicy.internal(url));
    }
    @Test public void rejectsExternalAndLocalOrSpoofedOrigins() {
        for (String url : new String[]{null,"", "https://evil.example/", "http://bob-private-scanner.onrender.com/", "https://bob-private-scanner.onrender.com.evil.example/", "https://bob-private-scanner.onrender.com@evil.example/", "https://user@bob-private-scanner.onrender.com/", "https://bob-private-scanner.onrender.com:8443/", "file:///data/data/", "content://private", "intent://scan", "javascript:alert(1)"}) assertFalse(String.valueOf(url),NavigationPolicy.internal(url));
    }
}

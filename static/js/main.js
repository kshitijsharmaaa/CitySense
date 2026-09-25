/**
 * CitySense - Main Client JavaScript
 * Handles component interactivity, dismissible alerts, and UI triggers.
 */

document.addEventListener('DOMContentLoaded', function () {
  console.log('CitySense UI Engine initialized successfully.');

  // Initialize Bootstrap Tooltips if present
  var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new bootstrap.Tooltip(tooltipTriggerEl);
  });

  // Auto-dismiss alert notifications after 5 seconds if marked with auto-dismiss class
  var autoDismissAlerts = document.querySelectorAll('.cs-alert-autodismiss');
  autoDismissAlerts.forEach(function (alertEl) {
    setTimeout(function () {
      var bsAlert = bootstrap.Alert.getOrCreateInstance(alertEl);
      if (bsAlert) {
        bsAlert.close();
      }
    }, 5000);
  });
});

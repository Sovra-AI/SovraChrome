// Invoking the action grants activeTab on this tab before the panel opens.
chrome.action.onClicked.addListener(tab => {
  chrome.sidePanel.open({windowId: tab.windowId});
});

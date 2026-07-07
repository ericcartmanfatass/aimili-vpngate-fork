function render(){
  const activeNode = getActiveNodeForRender();
  renderActiveNodeCard(activeNode);
  const shown = getFilteredNodes();
  renderSummaryStatus(activeNode);
  renderProxyStatusCard();
  updateFavPanelUI();
  renderNodeRows(activeNode, shown);
}

charm = {
  name  = "tenant-service"
  units = 1
  base  = "ubuntu@22.04"
  trust = true
  config = {
    "salesforce_domain" : "https://canonicalhr--staging.sandbox.my.salesforce.com",
    "salesforce_enabled" : true,
    "https_proxy" : "http://squid.ps6.internal:3128",
    "http_proxy" : "http://squid.ps6.internal:3128",
    "no_proxy" : "10.142.162.0/24,10.100.0.0/16,10.200.0.0/16,localhost,127.0.0.1,0.0.0.0,ppa.launchpad.net,launchpad.net,canonical.com,gcr.io,svc.cluster.local"
  }
}

<?xml version="1.0" ?>
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output omit-xml-declaration="yes" indent="yes"/>
  <xsl:template match="node()|@*">
     <!-- Do not change any nonrelevant node -->
     <xsl:copy>
       <xsl:apply-templates select="node()|@*"/>
     </xsl:copy>
  </xsl:template>

  <xsl:template match="/network/ip[@family='ipv4']/dhcp/range">
    <!-- Change any IPv4 network with the following mutation -->
    <xsl:copy>
      <xsl:attribute name="start">
        <!-- Transform start range of e.g. "192.168.122.2" to "192.168.122.128" -->
        <xsl:value-of select="concat(substring(@start, 1, string-length(@start) - 2),'.128')" />
      </xsl:attribute>
      <xsl:apply-templates select="@*[not(local-name()='start')]|node()"/>
    </xsl:copy>
  </xsl:template>

  <xsl:template match="/network/ip[@family='ipv6']/dhcp/range">
    <!-- Change any IPv6 network with the following mutation -->
    <xsl:copy>
      <xsl:attribute name="end">
        <!-- Transform end range of e.g. "1001:db8::fe" to "1001:db8::63" -->
        <xsl:value-of select="concat(substring(@end, 1, string-length(@end) - 2),'63')" />
      </xsl:attribute>
      <xsl:apply-templates select="@*[not(local-name()='end')]|node()"/>
    </xsl:copy>
  </xsl:template>

</xsl:stylesheet>

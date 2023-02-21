<?xml version="1.0"?>
<xsl:stylesheet version="1.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output omit-xml-declaration="yes" indent="yes" />
  <xsl:template match="node()|@*">
    <xsl:copy>
      <xsl:apply-templates select="node()|@*" />
    </xsl:copy>
  </xsl:template>

  <xsl:template match="/domain/devices/console">
    <xsl:copy>
      <xsl:copy-of select="@*" />
        <xsl:copy-of select="node()" />
        <log
        file="/var/log/libvirt/qemu/{/domain/name}-console.log" append="on" />
    </xsl:copy>
  </xsl:template>

  <!-- use SCSI cdrom drive as IDE/SATA is not available on ARM machine type -->
  <xsl:template match="/domain/devices/disk[@device='cdrom']/target/@bus">
    <xsl:attribute name="bus">
      <xsl:value-of select="'scsi'" />
    </xsl:attribute>
  </xsl:template>

  <!-- rename cdrom drive to avoid clashes with other disks -->
  <xsl:template match="/domain/devices/disk[@device='cdrom']/target/@dev">
    <xsl:attribute name="dev">
      <xsl:value-of select="'vdz'" />
    </xsl:attribute>
  </xsl:template>
</xsl:stylesheet>

package com.example.testsampleapp.model;

import java.time.LocalDateTime;

public class Customer {
    private Integer id;
    private String name;
    private String memberRank;
    private Integer birthMonth;
    private String region;
    private Boolean firstOrderFlag;
    private LocalDateTime registeredAt;

    public Integer getId() { return id; }
    public void setId(Integer id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getMemberRank() { return memberRank; }
    public void setMemberRank(String memberRank) { this.memberRank = memberRank; }

    public Integer getBirthMonth() { return birthMonth; }
    public void setBirthMonth(Integer birthMonth) { this.birthMonth = birthMonth; }

    public String getRegion() { return region; }
    public void setRegion(String region) { this.region = region; }

    public Boolean getFirstOrderFlag() { return firstOrderFlag; }
    public void setFirstOrderFlag(Boolean firstOrderFlag) { this.firstOrderFlag = firstOrderFlag; }

    public LocalDateTime getRegisteredAt() { return registeredAt; }
    public void setRegisteredAt(LocalDateTime registeredAt) { this.registeredAt = registeredAt; }
}
